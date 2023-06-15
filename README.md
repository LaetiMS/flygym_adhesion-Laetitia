## FlyGym: Gymnasium environments for NeuroMechFly

[**Documentation**](https://nely-epfl.github.io/flygym/)

This package implements [Gymnasium](https://gymnasium.farama.org) environments for NeuroMechFly ([paper](https://doi.org/10.1038/s41592-022-01466-7), [code](https://github.com/NeLy-EPFL/NeuroMechFly)), a neuromechanical model of the fruit fly _Drosophila melanogaster_. Gymnasium is "a standard API for reinforcement learning, and a diverse collection of reference environments." The environments in this package serve as wrappers to provide a unified interface to interact with fly model in different physics simulators (PyBullet, MuJoCo, Isaac Gym).

The FlyGym repository was forked in the scopes of my Bachelor Project, to implement adhesion onto the existing NeuroMechFly Model. 

**Bachelor Project description**: 
The NeuroMechFly model does not have the Drosophila Melanogasters adhesive organs. The adhesive organs, called pulvillus, and the claw can be found on the pretarsus of each leg and are used by the fly to climb and walk rough surfaces. The presence / absence of these structures influence the flies capacity to walk and the gait that the fly uses. 
This project aims to lay down the groundworks of adhesion so that the walking fly can use adhesion in future works and thus make the simulations closer to reality. 

Quick overview of the notebooks developed for this project: 

- ***BrickOnCeiling.ipynb***: Adding an adhesion actuator to an XML file. Accessing gravity during the simulation. NB: accessing the adhesion actuator that was added externally causes an error. 
- ***mujoco_singleleg_grid.ipynb***: Perform grid search to find maximal gain value necessary for a single leg to adhere to the ceiling. 
- ***mujoco_contact_forces.ipynb***: Analyze the relationship between contact forces and adhesion on a static nonsymmetric fly. The contact forces are filtered with a median filter.  
- ***loop_single_step.ipynb*** : Use the single step data to create a walking fly that uses a tripod gait for a specified number of steps. Methods to amplify specific angle motion as well as a method to custom generate the number of steps in the simulation wanted.  
- ***loop_single_step_bipod.ipynb*** : Use the single step data to create a walking fly that uses a bipod gait for a specified number of steps. 
- ***mujoco_prerun_adhesion.ipynb***: Offline calculation of adhesion. Computes the derivative of the contact forces of each Tarsus5 / the sum of all Tarsi before any adhesion. Then reruns the simulation once adhesion is applied. Adhesion is on when the derivative is positive or positive and equal. 
- ***mujoco_prerun_adhesion_copy.ipynb***: Allows to do the grid search for prerun adhesion.

