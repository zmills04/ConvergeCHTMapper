"""Main Function

Contains the main function called by SLURM batch script to
start simulations and the main loop for running the iterative
CONVERGE simulations. Main loop checks for convergence after
each iteration and exits once converged.

Methods
-------
mainLoop: main loop iterating between combustion and
    coolant simulations while checking for convergence.
__main__: Function called by SLURM batch script that checks
    current state of run (if new or a restart) and begins mainLoop
"""

import os
import numpy as np
import h5py as hpy
import time as TimeMod
from .helperFuncs import *


def mainLoop(runInfo):
    """Main loop of job. Iteratively calls functions to run combustion and
    coolant simulations and maps data in between simulations. Loop will break
    in the event that the mapped data converges or an error is encountered.
    
    Parameters
    ----------
    runInfo: RunInfoClass
        Stores simulation state and run settings
    """

    while True:
        iterationTimeStart = TimeMod.time()
        IO.writeToStdOutFile('Iteration ' + str(runInfo['iter']) + ':')

        combSuccess = performCombustionStep(runInfo)

        # Just in case sim error was not set in runInfo
        if combSuccess == False:
            runInfo.setSimError()

        # Check if job has completed or an error has occurred
        if runInfo.checkJobComplete() or runInfo.checkErrors():
            break

        coolSuccess = performCoolantStep(runInfo)
        # Just in case sim error was not set in runInfo
        if coolSuccess == False:
            runInfo.setSimError()

        iterationTimeHours = 1./3600.*(TimeMod.time() - iterationTimeStart)
        iterationTimeDays = int(np.floor(iterationTimeHours / 24.))
        iterationTimeHours -= float(iterationTimeDays)*24.
        IO.writeToStdOutFile('Iteration {0} took {1} days and {2} hours to \
complete\n\n'.format(runInfo['iter'], iterationTimeDays, iterationTimeHours),1)

        if runInfo.checkJobComplete() or runInfo.checkErrors():
            break

        IO.writeToStdOutFile('\tBoundary heat transfer not converged, continuing \
iterations\n\n')


    # If loop broken because of error, print message saying error caused halt
    # to job in stderr
    if runInfo.checkErrors():
        IO.writeToStdErrFile('\n\nHTC Simulation encountered error and has \
halted after {0} iterations'.format(runInfo['iter']))

    # If successfully completed, print message saying job was successful to
    # stdout
    else:
        IO.writeToStdOutFile('\n\nHTC Simulation completed after {0} \
iterations'.format(runInfo['iter']))

    # runInfo will be written one last time to ensure that last state is
    # written to file for failed runs, this will ensure the last iteration
    # info (for entire loop and individual simulations) is written out
    # in event of error being thrown. For completed runs, this will ensure
    # that htcRunInfo.yaml file has correct flags set if Job restarted
    # incorrectly. In the event of restart, readRunInfo will read in 
    # htcRunInfo to determine last state of simulation.
    runInfo.write()


if __name__ == "__main__":
    curStateRet, runInfo = checkCurrentState()
    if curStateRet == False:
        IO.writeToStdErrFile('Error itinializing job. Cancelling job')
    else:
        IO.writeToStdOutFile('\nJob successfully initialized. Entering main loop')
        IO.writeToStdOutFile('Running Converge Simulations using: {0}'.format(
            runInfo.runCmd()))
        mainLoop(runInfo)