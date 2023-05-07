import numpy as np
import yaml
import imageio
import copy
import logging
from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path
from scipy.spatial.transform import Rotation as R

import gymnasium as gym
from gymnasium import spaces
from gymnasium.core import ObsType

try:
    import mujoco
    import dm_control
    from dm_control import mjcf
    from dm_control.utils import transformations
except ImportError:
    raise ImportError(
        'MuJoCo prerequisites not installed. Please install the prerequisites '
        'by running `pip install flygym[mujoco]` or '
        '`pip install -e ."[mujoco]"` if installing locally.'
    )

from flygym.terrain.mujoco_terrain import \
    FlatTerrain, Ball, GappedTerrain, ExtrudingBlocksTerrain
from flygym.util.data import mujoco_groundwalking_model_path #DONE: modified the groundwalking_nmf_mjc_nofloor_230416_bendTarsus.xml file by adding adhesion actuators
from flygym.util.data import default_pose_path, stretch_pose_path, \
    zero_pose_path
from flygym.util.config import all_leg_dofs, all_adhesion_bodies, all_tarsi_collisions_geoms, all_legs_collisions_geoms, all_legs_collisions_geoms_no_coxa, tripod_adhesion_bodies, single_leg_adhesion_bodies

_init_pose_lookup = {
    'default': default_pose_path,
    'stretch': stretch_pose_path,
    'zero': zero_pose_path,
}
_collision_lookup = {
    'all': 'all',
    'legs': all_legs_collisions_geoms,
    'legs-no-coxa': all_legs_collisions_geoms_no_coxa,
    'tarsi': all_tarsi_collisions_geoms,
    'none': []
}
_adhesion_lookup = {
    'all': all_adhesion_bodies,
    'tripod': tripod_adhesion_bodies,
    'single_leg': single_leg_adhesion_bodies,
}

_default_terrain_config = {
    'flat': {
        'size': (50_000, 50_000),
        'friction': (1, 0.005, 0.0001),
        'fly_pos': (0, 0, 300),
        'fly_orient': (0, 1, 0, 0.1)
    },
    'gapped': {
        'x_range': (-10_000, 10_000),
        'y_range': (-10_000, 10_000),
        'friction': (1, 0.005, 0.0001),
        'gap_width': 200,
        'block_width': 1000,
        'gap_depth': 2000,
        'fly_pos': (0, 0, 600),
        'fly_orient': (0, 1, 0, 0.1)
    },
    'blocks': {
        'x_range': (-10_000, 10_000),
        'y_range': (-10_000, 10_000),
        'friction': (1, 0.005, 0.0001),
        'block_size': 1000,
        'height_range': (300, 300),
        'rand_seed': 0,
        'fly_pos': (0, 0, 600),
        'fly_orient': (0, 1, 0, 0.1)
    },
    'ball': {
        'radius': ...,
        'fly_pos': (0, 0, ...),
        'fly_orient': (0, 1, 0, ...),
    },
}
_default_physics_config = {
    'joint_stiffness': 2500,
    'friction': (1, 0.005, 0.0001),
    'gravity': (0, 0, -9.81e5), #important
    'gravity_inv': (0,0,9.81e5), 
}
_default_render_config = {
    'saved': {'window_size': (640, 480), 'playspeed': 1.0, 'fps': 60,
              'camera': 1},
    'headless': {}
}


class NeuroMechFlyMuJoCo(gym.Env):
    """A NeuroMechFly environment using MuJoCo as the physics engine.

    Attributes
    ----------
    render_mode : str
        The rendering mode. Can be 'headless' (no graphic rendering),
        'viewer' (display rendered images as the simulation takes
        place), or 'saved' (saving the rendered video to a file under
        ``output_dir`` at the end of the simulation).
    render_config : Dict[str, Any]
        Rendering configuration. Allowed parameters depend on the
        rendering mode (``render_mode``).
    actuated_joints : List[str]
        List of actuated joints.
    timestep : float
        Simulation timestep in seconds.
    output_dir : Path
        Directory to save simulation data.
    terrain : str
        The terrain type. Can be 'flat' or 'ball'.
    terrain_config : Dict[str, Any]
        Terrain configuration. Allowed parameters depend on the terrain
        type (``terrain``).
    physics_config : Dict[str, Any]
        Physics configuration (gravity, joint stiffness, etc).
    control : str
        The joint controller type. Can be 'position', 'velocity', or
        'torque'.
    init_pose : str
        Which initial pose to start the simulation from. Currently only
        'default' is implemented.
    action_space : Dict[str, gym.spaces.Box]
        Definition of the simulation's action space as a Gym
        environment.
    observation_space : Dict[str, gym.spaces.Box]
        Definition of the simulation's observation space as a Gym
        environment.
    model : dm_control.mjcf.RootElement
        The MuJoCo model.
    physics : dm_control.mujoco.Physics
        The MuJoCo physics simulation.
    actuators : Dict[str, dm_control.mjcf.Element]
        The MuJoCo actuators.
    actuators_adhesion: #TO DO: add documentation
        The MuJoCo adhesion actuators. 
    joint_sensors : Dict[str, dm_control.mjcf.Element]
        The MuJoCo sensors on joint positions, velocities, and forces.
    body_sensors : Dict[str, dm_control.mjcf.Element]
        The MuJoCo sensors on thorax position and orientation.
    curr_time : float
        The (simulated) time elapsed since the last reset (in seconds).
    self_contact_pairs: List[dm_control.mjcf.Element]
        The MuJoCo geom pairs that can be in contact with each other
    self_contact_pair_names: List[str]
        The names of the MuJoCo geom pairs that can be in contact with
        each other
    floor_contact_pairs: List[dm_control.mjcf.Element]
        The MuJoCo geom pairs that can be in contact with the floor
    floor_contact_pair_names: List[str]
        The names of the MuJoCo geom pairs that can be in contact with
        the floor
    touch_sensors: List[dm_control.mjcf.Element]
        The MuJoCo touch sesnor used to conpute contact forces
    end_effector_sensors: List[dm_control.mjcf.Element]
        The set of position sensors on the end effectors

    """
    _metadata = {
        'render_modes': ['headless', 'viewer', 'saved'],
        'terrain': ['flat', 'gapped', 'blocks', 'ball'],
        'control': ['position', 'velocity', 'torque'],
        'init_pose': ['default', 'stretch', 'zero']
    }

    def __init__(self,
                 render_mode: str = 'saved',
                 render_config: Dict[str, Any] = {},
                 actuated_joints: List = all_leg_dofs,
                 adhesion: bool = True,
                 actuated_bodies: str = 'all',
                 actuators_adhesion_gain: float = 2500,
                 collision_tracked_geoms: List = all_tarsi_collisions_geoms,
                 timestep: float = 0.0001,
                 output_dir: Optional[Path] = None,
                 terrain: str = 'flat',
                 terrain_config: Dict[str, Any] = {},
                 physics_config: Dict[str, Any] = {},
                 control: str = 'position',
                 init_pose: str = 'default',
                 floor_collisions_geoms: str = 'legs',
                 self_collisions_geoms: str = 'legs',
                 ) -> None:
        """Initialize a MuJoCo-based NeuroMechFly environment.

        Parameters
        ----------
        render_mode : str, optional
            The rendering mode. Can be 'headless' (no graphic rendering),
            'viewer' (display rendered images as the simulation takes
            place), or 'saved' (saving the rendered video to a file under
            ``output_dir`` at the end of the simulation). By default
            'saved'.
        render_config : Dict[str, Any], optional
            Rendering configuration. Allowed parameters depend on the
            rendering mode (``render_mode``). See :ref:`mujoco_config`
            for detailed options.
        actuated_joints : List, optional
            List of actuated joint DoFs, by default all leg DoFs
        adhesion : bool, optional
            True : General Adhesion is on
            False : General Adhesion is off 
        actuated_bodies : str, optional
            The stance of actuated bodies for static adhesion simulation. It can be 'all', 'tripod' or 'single_leg'
        timestep : float, optional
            Simulation timestep in seconds, by default 0.0001
        output_dir : Path, optional
            Directory to save simulation data (by default just the video,
            but you can extend this class to save additional data).
            If ``None``, no data will be saved. By default None
        terrain : str, optional
            The terrain type. Can be 'flat' or 'ball'. By default 'flat'
        terrain_config : Dict[str, Any], optional
            Terrain configuration. Allowed parameters depend on the
            terrain type. See :ref:`mujoco_config` for detailed options.
        physics_config : Dict[str, Any], optional
            Physics configuration (gravity, joint stiffness, etc). See
            :ref:`mujoco_config` for detailed options.
        control : str, optional
            The joint controller type. Can be 'position', 'velocity', or
            'torque'., by default 'position'
        init_pose : str, optional
            Which initial pose to start the simulation from. Currently only
            'default' is implemented.
        floor_collisions_geoms :str
            Which set of collisions should collide with the floor. Can be
            'all', 'legs', or 'tarsi'.
        self_collisions_geoms : str
            Which set of collisions should collide with each other. Can be
            'all', 'legs', 'legs-no-coxa', 'tarsi', or 'none'.
        """
        self.render_mode = render_mode
        self.render_config = copy.deepcopy(_default_render_config[render_mode])
        self.render_config.update(render_config)
        self.actuated_joints = actuated_joints
        self.adhesion = adhesion
        self.actuated_adhesion_bodies = _adhesion_lookup[actuated_bodies] #added
        self.collision_tracked_geoms = collision_tracked_geoms
        self.timestep = timestep
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = output_dir
        self.terrain = terrain
        self.terrain_config = copy.deepcopy(_default_terrain_config[terrain])
        self.terrain_config.update(terrain_config)
        self.physics_config = copy.deepcopy(_default_physics_config)
        self.physics_config.update(physics_config)
        self.control = control

        # Define action and observation spaces
        num_dofs = len(actuated_joints)
        bound = np.pi if control == 'position' else np.inf
        self.action_space = {
            'joints': spaces.Box(low=-bound, high=bound, shape=(num_dofs,)),
            #'adhesion': spaces.Discrete(n=2, start=0) #TO DO: change this if you do not want discrete adhesion values 
            'adhesion': spaces.Box(low=0.0, high=1.0)
        }
        self.observation_space = {
            # joints: shape (3, num_dofs): (pos, vel, torque) of each DoF
            'joints': spaces.Box(low=-np.inf, high=np.inf,
                                 shape=(3, num_dofs)),
            # fly: shape (4, 3):
            # 0th row: x, y, z position of the fly in arena
            # 1st row: x, y, z velocity of the fly in arena
            # 2nd row: orientation of fly around x, y, z axes
            # 3rd row: rate of change of fly orientation
            'fly': spaces.Box(low=-np.inf, high=np.inf, shape=(4, 3)),
            'tarsus_body': spaces.Box(low=-np.inf, high=np.inf, shape=(4,5)) #TO DO: INCOMPLETE
        }

        # Load NMF model
        self.model = mjcf.from_path(mujoco_groundwalking_model_path)
        self.model.option.timestep = timestep
        if init_pose not in self._metadata['init_pose']:
            raise ValueError(f'Invalid init_pose: {init_pose}')
        with open(_init_pose_lookup[init_pose]) as f:
            init_pose = {k: np.deg2rad(v)
                         for k, v in yaml.safe_load(f)['joints'].items()}
        self.init_pose = {k: v for k, v in init_pose.items()
                          if k in actuated_joints}

        # Fix unactuated joints and define list of actuated joints
        # for joint in model.find_all('joint'):
        #     if joint.name not in actuated_joints:
        #         joint.type = 'fixed'
        self.actuators = [
            self.model.find('actuator', f'actuator_{control}_{joint}')
            for joint in actuated_joints
        ]
        self.actuators_adhesion = []
        self.actuators_adhesion_gain = actuators_adhesion_gain
        for body_name in self.actuated_adhesion_bodies: 
            self.actuators_adhesion.extend([
                self.model.actuator.add('adhesion', name =f"{body_name}_adhesion", gain=f"{self.actuators_adhesion_gain}", body=body_name, ctrlrange="0 1000000", forcerange="-inf inf") #gain ="500" is too week
            ])
        print(f'{self.actuators_adhesion} actuators _adhesion')

        # Initialize contact force and previous contact state
        self.contact_force = {}
        self.prev_contact = {}
        for body_name in self.actuated_adhesion_bodies:
            self.contact_force[body_name] = 0.0
            self.prev_contact[body_name] = False
        # Add sensors
        self.joint_sensors = []
        for joint in actuated_joints:
            self.joint_sensors.extend([
                self.model.sensor.add('jointpos',
                                      name=f'jointpos_{joint}', joint=joint),
                self.model.sensor.add('jointvel',
                                      name=f'jointvel_{joint}', joint=joint),
                self.model.sensor.add('actuatorfrc',
                                      name=f'actuatorfrc_position_{joint}',
                                      actuator=f'actuator_position_{joint}'),
                self.model.sensor.add('actuatorfrc',
                                      name=f'actuatorfrc_velocity_{joint}',
                                      actuator=f'actuator_velocity_{joint}'),
                self.model.sensor.add('actuatorfrc',
                                      name=f'actuatorfrc_motor_{joint}',
                                      actuator=f'actuator_torque_{joint}'),
            ])

        self.body_sensors = [
            self.model.sensor.add('framepos', name='thorax_pos',
                                  objtype='body', objname='Thorax'),
            self.model.sensor.add('framelinvel', name='thorax_linvel',
                                  objtype='body', objname='Thorax'),
            self.model.sensor.add('framequat', name='thorax_quat',
                                  objtype='body', objname='Thorax'),
            self.model.sensor.add('frameangvel', name='thorax_angvel',
                                  objtype='body', objname='Thorax')
        ]

        self_collisions_geoms = _collision_lookup[self_collisions_geoms]
        if self_collisions_geoms == "all":
            self_collisions_geoms = []
            for geom in self.model.find_all('geom'):
                if "collision" in geom.name:
                    self_collisions_geoms.append(geom.name)

        self.self_contact_pairs = []
        self.self_contact_pairs_names = []

        for geom1 in self_collisions_geoms:
            for geom2 in self_collisions_geoms:
                is_duplicate = f'{geom1}_{geom2}' in self.self_contact_pairs_names
                if geom1 != geom2 and not is_duplicate:

                    # Do not add contact if the parent bodies have a child parent relationship
                    body1 = self.model.find("geom", geom1).parent
                    body2 = self.model.find("geom", geom2).parent
                    body1_children = [child.name
                                      for child in body1.all_children()
                                      if child.tag == 'body']
                    body2_children = [child.name
                                      for child in body2.all_children()
                                      if child.tag == 'body']

                    if not (body1.name == body2.name or
                            body1.name in body2_children or
                            body2.name in body1_children or
                            body1.name in body2.parent.name or
                            body2.name in body1.parent.name):
                        contact_pair = self.model.contact.add(
                            "pair",
                            name=f'{geom1}_{geom2}',
                            geom1=geom1,
                            geom2=geom2,
                            solref="-1000000 -10000",
                            margin=0.0
                        )
                        self.self_contact_pairs.append(contact_pair)
                        self.self_contact_pairs_names.append(f'{geom1}_{geom2}')

        self.end_effector_sensors = []
        self.end_effector_names = [] #TO DO: This might be very useful!
        for body in self.model.find_all('body'):
            if "Tarsus5" in body.name:
                self.end_effector_names.append(body.name)
                end_effector_sensor = self.model.sensor.add(
                    'framepos', name=f'{body.name}_pos',
                    objtype='body', objname=body.name
                )
                self.end_effector_sensors.append(end_effector_sensor) #remove: i added the brackets [end_effector_sensor]

        ## Add sites and touch sensors
        self.touch_sensors = []

        for tracked_geom in collision_tracked_geoms:
            geom = self.model.find("geom", tracked_geom)
            body = geom.parent
            site = body.add('site', name=f'site_{geom.name}',
                            size=np.ones(3) * 1000,
                            pos=geom.pos, quat=geom.quat, type='sphere',
                            group=3)
            touch_sensor = self.model.sensor.add('touch',
                                                 name=f'touch_{geom.name}',
                                                 site=site.name)
            self.touch_sensors.append( touch_sensor)

        # Add arena and put fly in it
        if terrain == 'flat':
            my_terrain = FlatTerrain(
                size=self.terrain_config['size'],
                friction=self.terrain_config['friction']
            )
            my_terrain.spawn_entity(self.model,
                                    rel_pos=self.terrain_config['fly_pos'],
                                    rel_angle=self.terrain_config['fly_orient'])
            arena = my_terrain.arena
        elif terrain == 'gapped':
            my_terrain = GappedTerrain(
                x_range=self.terrain_config['x_range'],
                y_range=self.terrain_config['y_range'],
                gap_width=self.terrain_config['gap_width'],
                block_width=self.terrain_config['block_width'],
                gap_depth=self.terrain_config['gap_depth'],
                friction=self.terrain_config['friction']
            )
            my_terrain.spawn_entity(self.model,
                                    rel_pos=self.terrain_config['fly_pos'],
                                    rel_angle=self.terrain_config['fly_orient'])
            arena = my_terrain.arena
        elif terrain == 'blocks':
            my_terrain = ExtrudingBlocksTerrain(
                x_range=self.terrain_config['x_range'],
                y_range=self.terrain_config['y_range'],
                block_size=self.terrain_config['block_size'],
                height_range=self.terrain_config['height_range'],
                rand_seed=self.terrain_config['rand_seed'],
                friction=self.terrain_config['friction']
            )
            my_terrain.spawn_entity(self.model,
                                    rel_pos=self.terrain_config['fly_pos'],
                                    rel_angle=self.terrain_config['fly_orient'])
            arena = my_terrain.arena
        elif terrain == 'ball':
            raise NotImplementedError

        # Add collision between the ground and the fly
        floor_collisions_geoms = _collision_lookup[floor_collisions_geoms]

        self.floor_contact_pairs = []
        self.floor_contact_pairs_names = []
        ground_id = 0

        if floor_collisions_geoms == "all":
            floor_collisions_geoms = []
            for geom in self.model.find_all('geom'):
                if "collision" in geom.name:
                    floor_collisions_geoms.append(geom.name)

        for geom in arena.find_all("geom"):
            is_ground = (geom.name is None or
                         not ("visual" in geom.name or
                              "collision" in geom.name))
            for animat_geom_name in floor_collisions_geoms:
                if is_ground:
                    if geom.name is None:
                        geom.name = f'groundblock_{ground_id}'
                        ground_id += 1

                    floor_contact_pair = arena.contact.add(
                        "pair",
                        name=f'{geom.name}_{animat_geom_name}',
                        geom1=f'Animat/{animat_geom_name}',
                        geom2=f'{geom.name}',
                        solref="-1000000 -10000",
                        margin=0.0,
                        friction=np.repeat(
                            np.mean([self.physics_config['friction'],
                                     self.terrain_config['friction']], axis=0),
                            (2, 1, 2)
                        )
                    )
                    self.floor_contact_pairs.append(floor_contact_pair)
                    self.floor_contact_pairs_names.append(
                        f'{geom.name}_{animat_geom_name}'
                    )

        arena.option.timestep = timestep
        self.physics = mjcf.Physics.from_mjcf_model(arena)
        self.curr_time = 0
        self._last_render_time = -np.inf
        if render_mode != 'headless':
            self._eff_render_interval = (self.render_config['playspeed'] /
                                         self.render_config['fps'])
        self._frames = []

        # Ad hoc changes to gravity, stiffness, and friction
        for geom in [geom.name for geom in arena.find_all('geom')]:
            if 'collision' in geom:
                self.physics.model.geom(f'Animat/{geom}').friction = \
                    self.physics_config['friction']

        for joint in self.actuated_joints:
            if joint is not None:
                self.physics.model.joint(f'Animat/{joint}').stiffness = \
                    self.physics_config['joint_stiffness']

        self.physics.model.opt.gravity = self.physics_config['gravity']

        # set complaint tarsus
        all_joints = [joint.name for joint in arena.find_all('joint')]
        self._set_compliant_Tarsus(all_joints, stiff=3.5e5, damping=100)
        # set init pose
        self._set_init_pose(self.init_pose)

    def _set_init_pose(self, init_pose: Dict[str, float]):
        with self.physics.reset_context():
            for i in range(len(self.actuated_joints)):
                if ((self.actuators[i].joint.name in self.actuated_joints) and
                        (self.actuators[i].joint.name in init_pose)):
                    angle_0 = init_pose[self.actuators[i].joint.name]
                    self.physics.named.data.qpos[
                        f'Animat/{self.actuators[i].joint.name}'
                    ] = angle_0
            if self.adhesion:
                print(self.actuators_adhesion)
                for adh_act in self.actuators_adhesion:
                    self.physics.bind(adh_act).ctrl = 1 #pay attention it doesnt work for some reason if you write: self.physics.model.bind(adh_act).ctrl
            else:
                for adh_act in self.actuators_adhesion:
                    self.physics.bind(adh_act).ctrl = 0 
                

    def _set_compliant_Tarsus(self,
                              all_joints: List,
                              stiff: float = 0.0,
                              damping: float = 100):
        """Set the Tarsus2/3/4/5 to be compliant by setting the
        stifness and damping to a low value"""
        for joint in all_joints:
            if joint is None:
                continue
            if ('Tarsus' in joint) and (not 'Tarsus1' in joint):
                self.physics.model.joint(f'Animat/{joint}').stiffness = stiff
                # self.physics.model.joint(f'Animat/{joint}').springref = 0.0
                self.physics.model.joint(f'Animat/{joint}').damping = damping

        self.physics.reset()

    def set_output_dir(self, output_dir: str):
        """Set the output directory for the environment.
        Allows the user to change the output directory after the
        environment has been initialized. If the directory does not
        exist, it will be created.
        Parameters
        ----------
        output_dir : str
            The output directory.
        """
        output_dir = Path.cwd() / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = output_dir

    def reset(self) -> Tuple[ObsType, Dict[str, Any]]:
        """Reset the Gym environment.

        Returns
        -------
        ObsType
            The observation as defined by the environment.
        Dict[str, Any]
            Any additional information that is not part of the
            observation. This is an empty dictionary by default but
            the user can override this method to return additional
            information.
        """
        self.physics.reset()
        self.curr_time = 0
        self._set_init_pose(self.init_pose)
        self._frames = []
        self._last_render_time = -np.inf
        return self._get_observation(), self._get_info()

    def step(self, action: ObsType
             ) -> Tuple[ObsType, float, bool, Dict[str, Any]]:
        """Step the Gym environment.

        Parameters
        ----------
        action : ObsType
            Action dictionary as defined by the environment's
            action space.

        Returns
        -------
        ObsType
            The observation as defined by the environment.
        Dict[str, Any]
            Any additional information that is not part of the
            observation. This is an empty dictionary by default but
            the user can override this method to return additional
            information.
        """
        self.physics.bind(self.actuators).ctrl = action['joints']
        self.physics.bind(self.actuators_adhesion).ctrl = action['adhesion'] #added
        self.physics.step()
        self.curr_time += self.timestep
        return self._get_observation(), self._get_info()

    def render(self):
        """Call the ``render`` method to update the renderer. It should
        be called every iteration; the method will decide by itself
        whether action is required."""
        if self.render_mode == 'headless':
            return
        if self.curr_time < self._last_render_time + self._eff_render_interval:
            return
        if self.render_mode == 'saved':
            width, height = self.render_config['window_size']
            camera = self.render_config['camera']
            img = self.physics.render(width=width, height=height,
                                      camera_id=camera)
            self._frames.append(img.copy())
            self._last_render_time = self.curr_time
        else:
            raise NotImplementedError

    def _get_observation(self) -> Tuple[ObsType, Dict[str, Any]]:
        # joint sensors
        joint_obs = np.zeros((3, len(self.actuated_joints)))
        joint_sensordata = self.physics.bind(self.joint_sensors).sensordata
        for i, joint in enumerate(self.actuated_joints):
            base_idx = i * 5
            # pos and vel
            joint_obs[:2, i] = joint_sensordata[base_idx:base_idx + 2]
            # torque from pos/vel/motor actuators
            joint_obs[2, i] = joint_sensordata[base_idx + 2:base_idx + 5].sum()
        joint_obs[2, :] *= 1e-9  # convert to N

        # fly position and orientation
        cart_pos = self.physics.bind(self.body_sensors[0]).sensordata
        cart_vel = self.physics.bind(self.body_sensors[1]).sensordata
        quat = self.physics.bind(self.body_sensors[2]).sensordata
        # ang_pos = transformations.quat_to_euler(quat)
        ang_pos = R.from_quat(quat).as_euler('xyz')  # explicitly use intrinsic
        ang_pos[0] *= -1  # flip roll?? 
        ang_vel = self.physics.bind(self.body_sensors[3]).sensordata
        fly_pos = np.array([cart_pos, cart_vel, ang_pos, ang_vel])

        # tarsi contact forces
        touch_sensordata = np.array(
            self.physics.bind(self.touch_sensors).sensordata)
        
        # adhesion activated or not?
        #HERE
        '''
        # Reset contact forces to zero
        for body_name in self.actuated_adhesion_bodies:
            self.contact_force[body_name] = 0.0
            
        # Check for contacts and update contact forces
        for i in range(self.physics.data.ncon):
            contact = self.physics.data.contact[i]
            geom1 = self.physics.named.data.geom_xpos[contact.geom1]
            geom2 = self.physics.named.data.geom_xpos[contact.geom2]    
            for body_name in self.actuated_adhesion_bodies:
                if f"{body_name}_collision" in (geom1, geom2):
                    if geom1 == f"{body_name}_collision":
                        print("hi")
                        contact_force = np.linalg.norm(contact.force)
                    else:
                        contact_force = -np.linalg.norm(contact.force)
                        
                    self.contact_force[body_name] += contact_force
                    
        # Update adhesion actuators based on contact forces
        for body_name in self.actuated_adhesion_bodies:
            if self.contact_force[body_name] > 0 and not self.prev_contact[body_name]:
                # Leg is pushing into floor
                self.actuators_adhesion[self.actuators_adhesion.index(f"{body_name}_adhesion")].ctrl = 1
                self.prev_contact[body_name] = True
            elif self.contact_force[body_name] <= 0 and self.prev_contact[body_name]:
                # Leg is lifting off floor
                self.actuators_adhesion[self.actuators_adhesion.index(f"{body_name}_adhesion")].ctrl = 0
                self.prev_contact[body_name] = False
        adhesion_obs = np.array(self.physics.bind(self.actuators_adhesion).ctrl) #added 0 or 1 if adhesion is active in a certain joint
        '''

        '''
        if self.adhesion:          
            for body_name in self.actuated_adhesion_bodies:
                adhesion = 0
                for contact in self.physics.named.data.contact[0]:
                    if contact.geom1 == self.physics.named.model.geom_name2id(f"{body_name}_collision") and contact.geom2 == self.physics.named.model.geom_name2id("floor_collision"):
                        force = np.linalg.norm(contact.fdir1 * contact.torque1)
                        if force > threshold:
                            adhesion = 1
                            break
                #self.physics.named.data.ctrl[f"{body_name}_adhesion"] = adhesion
                self.physics.bind([f"{body_name}_adhesion"]).ctrl = adhesion
            """    
            for adh_act in self.actuators_adhesion:
                    self.physics.bind(adh_act).ctrl = 0.1 #pay attention it doesnt work for some reason if you write: self.physics.model.bind(adh_act).ctrl
            """
        else:
            for adh_act in self.actuators_adhesion:
                self.physics.bind(adh_act).ctrl = 0 
        adhesion_obs = np.array(self.physics.bind(self.actuators_adhesion).ctrl) #added 0 or 1 if adhesion is active in a certain joint
        '''


        if self.adhesion:                        
            for adh_act in self.actuators_adhesion:
                    self.physics.bind(adh_act).ctrl = 1 #pay attention it doesnt work for some reason if you write: self.physics.model.bind(adh_act).ctrl
        
        else:
            for adh_act in self.actuators_adhesion:
                self.physics.bind(adh_act).ctrl = 0 
        adhesion_obs = np.array(self.physics.bind(self.actuators_adhesion).ctrl) #added 0 or 1 if adhesion is active in a certain joint   
        # end effector position
        ee_pos = self.physics.bind(self.end_effector_sensors).sensordata
        #print(ee_pos)

        return {
            'joints': joint_obs,
            'fly': fly_pos,
            'bodies_adhesion': adhesion_obs, #added : idea: record when adhesion is turned on
            'contact_forces': touch_sensordata,
            'end_effectors': ee_pos
        }

    def _get_info(self):
        return {}

    def save_video(self, path: Path):
        """Save rendered video since the beginning or the last
        ``reset()``, whichever is the latest.
        Only useful if ``render_mode`` is 'saved'.

        Parameters
        ----------
        path : Path
            Path to which the video should be saved.
        """
        if self.render_mode != 'saved':
            logging.warning('Render mode is not "saved"; no video will be '
                            'saved despite `save_video()` call.')

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        logging.info(f'Saving video to {path}')
        with imageio.get_writer(path, fps=self.render_config['fps']) as writer:
            for frame in self._frames:
                writer.append_data(frame)

    def close(self):
        """Close the environment, save data, and release any resources."""
        if self.render_mode == 'saved' and self.output_dir is not None:
            self.save_video(self.output_dir / 'video.mp4')
