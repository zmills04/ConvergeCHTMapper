"""Default values used for simulation setup parameters

Methods
-------
None
"""

# Tolerances to use for convergence checking
boundaryTempTolDefault = 5
fluxTolDefault = 10
fluidTempTolDefault = 5
htcTolDefault = 10

# If coolantOutput should be saved, set to True.
# otherwise, coolant data will be overwritten each iteration
saveCoolantOutputDefault = True

# Make zipped tarball of output data after moving into results folder
tarballResultsDefault = True

# Folder names for 2 simulations
combustionFolderDefault = 'combustion'
coolantFolderDefault = 'coolant'

# number of retry attempts after failed simulation before ending job
maxRestartsDefault = 5

# Starting Time in CAD
StartCADDefault = 125.0

boundaryTempDefault = 363.
boundaryHTCDefault = 5000.