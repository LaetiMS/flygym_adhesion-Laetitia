# DoF definitions
all_leg_dofs = [
    f'joint_{side}{pos}{dof}'
    for side in 'LR'
    for pos in 'FMH'
    for dof in ['Coxa', 'Coxa_roll', 'Coxa_yaw',
                'Femur', 'Femur_roll', 'Tibia', 'Tarsus1']
]
all_adhesion_bodies = [
    #name of all adhesion actuators
    f'{side}{pos}{dof}' #TO DO: potentiall its just this for the bodies : f'{side}{pos}{dof}' 
    for side in 'LR'
    for pos in 'FMH'
    #for dof in ['Tarsus1', 'Tarsus2', 'Tarsus3', 'Tarsus4', 'Tarsus5']
    for dof in ['Tarsus5']
]
tripod_adhesion_bodies = [elem for elem in ['LFTarsus5', 'LHTarsus5','RMTarsus5']]
single_leg_adhesion_bodies = ['LFTarsus5']

leg_dofs_3_per_leg = [
    f'joint_{side}{pos}{dof}'
    for side in 'LR'
    for pos in 'FMH'
    for dof in ['Coxa' if pos == 'F' else 'Coxa_roll', 'Femur', 'Tibia']
]
###### Geometries ######
all_tarsi_collisions_geoms = [
    f'{side}{pos}{dof}_collision'
    for side in 'LR'
    for pos in 'FMH'
    for dof in ['Tarsus1', 'Tarsus2', 'Tarsus3', 'Tarsus4', 'Tarsus5']
]
tripod_tarsi_collision_geoms = [
    f'{prefix}{dof}_collision'
    for prefix in ['LF', 'LH', 'RM']
    for dof in ['Tarsus1', 'Tarsus2', 'Tarsus3', 'Tarsus4', 'Tarsus5']
]
all_legs_collisions_geoms = [
    f'{side}{pos}{dof}_collision'
    for side in 'LR'
    for pos in 'FMH'
    for dof in ['Coxa', 'Femur', 'Tibia',
                'Tarsus1', 'Tarsus2', 'Tarsus3', 'Tarsus4', 'Tarsus5']
]

all_legs_collisions_geoms_no_coxa = [
    f'{side}{pos}{dof}_collision'
    for side in 'LR'
    for pos in 'FMH'
    for dof in ['Femur', 'Tibia',
                'Tarsus1', 'Tarsus2', 'Tarsus3', 'Tarsus4', 'Tarsus5']
]