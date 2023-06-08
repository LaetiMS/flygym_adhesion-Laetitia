## FlyGym: Gymnasium environments for NeuroMechFly

[**Documentation**](https://nely-epfl.github.io/flygym/)

This package implements [Gymnasium](https://gymnasium.farama.org) environments for NeuroMechFly ([paper](https://doi.org/10.1038/s41592-022-01466-7), [code](https://github.com/NeLy-EPFL/NeuroMechFly)), a neuromechanical model of the fruit fly _Drosophila melanogaster_. Gymnasium is "a standard API for reinforcement learning, and a diverse collection of reference environments." The environments in this package serve as wrappers to provide a unified interface to interact with fly model in different physics simulators (PyBullet, MuJoCo, Isaac Gym).

The FlyGym repository was forked in the scopes of my Bachelor Project, to implement adhesion onto the existing NeuroMechFly. 

Quick overview of the notebooks developed for this project: 
- ***loop_single_step.ipynb*** : Use the single step data to create a walking fly that uses a tripod gait for a specified number of steps. 
- ***mujoco_contact_forces.ipynb***: 
- ***mujoco_adhesion.ipynb***: 
- ***mujoco_prerun_adhesion.ipynb***: Offline calculation of adhesion. Computes the derivative of the contact forces of each Tarsus5 before any adhesion. Then reruns the simulation once adhesion is applied. Adhesion is on when the derivative is positive. 
- ***mujoco_singleleg_grid.ipynb***: Perform grid search to find maximal gain value necessary for a single leg to adhere to the ceiling. 
