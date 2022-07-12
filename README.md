# ConvergeCHTMapper
A python module for the automated execution of iterative CONVERGE simulations of both engine
combustion and coolant flow. This removes the need for CONVERGE users to manually perform
HTC mapping between coolant and combustion simulation and restart simulations.

Simulations must be set up using the following folder structure
```
SimulationFolder/
└───CoolantFolder/
│       convergeSimulationFiles.in
└───CombustionFolder
        convergeSimulationFiles.in
    engineToCoolantInterface.dat
    htc_map_64
    settings.yaml
    htcRunInfo.yaml
```

CoolantFolder and CombustionFolder contains the simulation files required by CONVERGE.
The mapper will change dictory into each folder and run the simulation as it iterates.

Settings.yaml provides the settings used by the mapper. See IO.py for more information
about what settings can be provided.

htcRunInfo.yaml is used by the mapper function to track current progress in the event
that it is restarted. This file is not needed when starting a new CHT simulation, but if
restarting, it must be included for the mapper to be able to determine how to restart.
Otherwise, it will start over.

engineToCoolantInterface.dat is the geometry file used by htc_map_64 to map
the heat transfer information between simulations. Any name can be used for this file, but
it must be specified in settings.yaml using the 'mapSurfaceFile' keyword.

These python files can be stored anywhere, but the location of runHTC.py must be added to
the path along with the converge binaries. Assuming that runHTC.py is in the path,
the iterative mapper can be started by a SLURM batch script with the line python runHTC.py.
It will automatically determine if the simulation is new, or if it is being restarted based
on the existance of htcRunInfo.yaml and output files in the coolant/combustion folder. Currently
this implementation is set up only for SLURM batch submissions, but any job scheduler should
be able to be used with some changes to the code.