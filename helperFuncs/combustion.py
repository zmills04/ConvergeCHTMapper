"""Functions for performing combustion phase of iteration

Contains all functions related to the combustion phase of the iteration,
including running CVG, mapping boundary data, checking convergence and
checking simulation for completion.

Methods
-------
mapCombustionDataAndCheckConvergence: maps data to coolant simulation,
    and checks for convergence in combustion simulation.
runSim: changes directory to dir containing combustion sim
    and calls actual CVG run function.
performCombustionStep: Calls CVG to run combustion simulation, restarting
    up to maxRestart times after failure.
prepCombustionRestartAfterFailure: Prepares combustion simulation for a
    restart after a job has been restarted.
restartCombustionDuringPostProcess: Restarts during the post-processing phase
    of the combustion part of the iteration.
checkCombustionCompleted: Additional check for checking combustion
    simulation completed using time in latest restart file.
"""

import numpy as np
import os
import time as TimeMod
# from .coolant import performCoolantStep
from .fileOps import clearErrorFiles, changeEntriesInFile, getRecentRestartFile
from .fileOps import moveRestartFiles, clearStartDoneFiles, moveResults
from .fileOps import getTimeFromRestartFile, callMoveFile, getRecentFile
from .fileOps import checkForBoundaryFiles, checkSimComplete
from .fileOps import correctTransferOutForRestart
from .testing import runTestSimulation
from . import IO
from .mapping import combustionBCtoCoolantBC, checkRunConvergence
from .mapping import renameBoundaryFiles
from .testing import getTimeFromRestartFileTest

def mapCombustionDataAndCheckConvergence(runInfo):
    """Maps boundary data from transfer.out for coolant simulation
    and checks for convergence by comparing with previous boundary
    values
    
    Parameters
    ----------
    runInfo: RunInfoClass
        Stores simulation state and run settings
    """

    # map data from combustion to coolant domain
    runInfo.setPostProcessStep('mapping','combustion')
    IO.writeToStdOutFile('Mapping boundary data from combustion to coolant \
simulation',2)
    combustionBCtoCoolantBC(runInfo)
    
    if runInfo.checkErrors():
        IO.writeToStdErrFile('Job being cancelled after mapping from combustion \
to coolant failed')
        return
    
    # check convergence and set value in runInfo
    runInfo.setPostProcessStep('convergenceCheck','combustion')
    IO.writeToStdOutFile('Checking convergence of combustion simulation',2)
    runInfo.setCombConvergence('comb',checkRunConvergence(runInfo,
        'combustion'))
    
    # rename boundary files to use in convergence checking
    runInfo.setPostProcessStep('boundaryFileRename','combustion')
    IO.writeToStdOutFile('Renaming files containing newest bounday data from \
combustion simulation',2)
    renameBoundaryFiles(runInfo,'combustion')


def runSim(runInfo):
    """Runs a converge simulation in the combustion directory stored
    in runInfo. Command to run simulation is obtained from environment
    variables if not provided in settings.yaml (variable name is CMD).
    Number of processors is obtained from environment variable if not 
    provided as nProcs in settings.yaml. Current implementation assumes
    SLURM as the workload manager, so the number of processors to run with
    is obtained from SLURM_NTASKS env variable. Default mpi job submission
    executable is mpirun. A different executable can be provided in
    settings.yaml (mpiExe). Default mpirun (or alterative provided in settings)
    option is '-np $NPROCS'. Alternative can be provided using mpiOptions
    variable. Note: when providing mpiOptions, user must define number of
    processors themselves as this will replace the default options, no be
    appended to it.

    Parameters
    ----------
    runInfo: RunInfoClass
        Object containing settings and run state
    """

    if runInfo.testing():
        runTestSimulation(runInfo.combustionFol(), runInfo)
        return

    os.chdir(runInfo.combustionFol())
    runCmd = runInfo.runCmd()
    os.system(runCmd)
    os.chdir('..')


def performCombustionStep(runInfo):
    """Runs combustion simulation, and calls appropriate functions for
    mapping boundaries, checking convergence, saving results/restart
    files, and preparing simulation for next iteration
    
    Parameters
    ----------
    runInfo: RunInfoClass
        Stores simulation state and run settings

    Returns
    -------
    float:
        Time elapsed during simulation.
    """

    IO.writeToStdOutFile('Starting combustion Step at ' + TimeMod.ctime(),1)

    # If boundary files are in combustion folder, boundary.in needs the
    # names of these files. Minimal computational cost to check, so its done
    # every iteration just in case something happens to one of the files
    checkForBoundaryFiles('combustion', runInfo)

    startTime = TimeMod.time()

    # Loop until combustion completes cycle or specified number of attempts
    # are reached before killing job
    while(True):

        runInfo['combIter'] += 1

        # write out run info with nonzero combIter info in case of restart
        runInfo.write()

        runSim(runInfo)

        if runInfo['ignoreCombRestart'] == True:
            os.system('rm {0}/restart.rst'.format(runInfo.coolantFol()))
            runInfo['ignoreCombRestart'] = False

        if checkSimComplete(runInfo.combustionFol()):
            break

        # remove any error files that might exist after failed simulation
        clearErrorFiles(runInfo.combustionFol())

        if runInfo.combIter() > runInfo['maxRestarts']:
            IO.writeToStdErrFile('Job being cancelled after combustion \
simulation has failed {0} consecutive times'.format(runInfo['maxRestarts']))
            runInfo.setSimError()
            return False

        IO.writeToStdOutFile('Combustion simulation did not complete on \
iteration {0}, restarting from last savepoint'.format(runInfo.combIter()),2)

        if prepCombustionRestartAfterFailure(runInfo) == False:
            IO.writeToStdErrFile('Job being cancelled after error restarting \
combustion simulation')
            runInfo.setSimError()
            return False

    combRunTime = TimeMod.time() - startTime
    
    # when mapping at beginning of simulation, restart file must be
    # removed to avoid errors
    if runInfo['ignoreCombRestart']:
        os.system('rm {0}/restart.rst'.format(runInfo.combustionFol()))
        runInfo['ignoreCombRestart'] = False

    # check to ensure simulation reached runInfo['combStopTime'], using testing
    # flag if this is a test
    combComplete = checkCombustionCompleted(runInfo.combustionFol(), 
                                            runInfo.combStopTime(), 
                                            runInfo.testing())

    if combComplete == False:
        IO.writeToStdErrFile('Job being cancelled after combustion simulation \
finished without reaching expected crank angle')
        runInfo.setSimError()
        return False
    
    IO.writeToStdOutFile('Combustion simulation completed successfully in \
{0} hours'.format(combRunTime/3600.),2)

    # map boundarys and check convergence
    mapCombustionDataAndCheckConvergence(runInfo)

    # Update inputs.in for next iteration
    runInfo.setPostProcessStep('updateInputs','combustion')
    newEntries = {
        'restart_number': int(1),
        'restart_flag': 1,
        'end_time': runInfo['combStopTime'] + 720.,
        'map_flag': 'OFF'
    }
    changeEntriesInFile('inputs.in', newEntries, runInfo.combustionFol())

    # copy output to save folder
    runInfo.setPostProcessStep('saveResults','combustion')
    IO.writeToStdOutFile('Saving combustion output',2)
    moveResults(runInfo.combustionFol(), runInfo.combStopTime(), runInfo)

    # rename and move restartFiles
    runInfo.setPostProcessStep('moveRestartFiles','combustion')
    IO.writeToStdOutFile('Moving restart files for combustion simulation',2)
    moveRestartFiles(runInfo.combustionFol())

    runInfo.setPostProcessStep('clearingFiles','combustion')
    clearStartDoneFiles(runInfo.combustionFol())

    # Update runInfo information
    runInfo.nextCombustionCycle()

    return True


def prepCombustionRestartAfterFailure(runInfo):
    """Makes necessary changes to CVG files for restarting simulation
    after a failure. Also corrects transfer.out file to remove any
    time steps written after last save point

    Parameters
    ----------
    runInfo: dict
        Stores simulation state

    Returns
    -------
    bool:
        Flag indicating successful correction of transfer.out file.
    """


    latestRst = getRecentRestartFile(runInfo.combustionFol())
    
    # combustion simulation will always generate a restart file at beginning
    # of run, if it doesn't, this indicates there is a problem in the
    # simulation setup
    if latestRst is None:
        # no existing restart file for combustion simulation. 
        IO.writeToStdErrFile('Combustion simulation failed before generating a \
restart file. Simulation cannot be restarted.')
        IO.writeToStdErrFile('Cancelling job.')
        return False
    
    latestRestartFull = runInfo.combustionFol() + '/' + latestRst
    if runInfo.testing():
        lastCombTime = getTimeFromRestartFileTest(latestRestartFull)
    else:
        lastCombTime = getTimeFromRestartFile(latestRestartFull)

    # if latest restart file is not restart.rst, rename it
    if latestRst != 'restart.rst':
        oldName = runInfo.combustionFol() + '/' + latestRst
        newName = runInfo.combustionFol() + '/restart.rst'    
        callMoveFile(oldName, newName)

    IO.writeToStdOutFile('Starting combustion step at t = {0} for attempt \
{1}'.format(lastCombTime, runInfo.combIter()),2)

    # combustion restart number will always be set at runInfo['combIter'] += 1
    # since with the exception of the first iteration, these simulations will
    # all be restarts and will start with 1 when runInfo['combIter'] = 0

    # restart_flag will always be set to 1 here just to ensure that its set
    # correctly before re-running simulation
    newEntries = {
        'restart_number': int(runInfo['combIter']+1),
        'restart_flag': 1,
        'map_flag': 'OFF'
    }
    changeEntriesInFile('inputs.in', newEntries, runInfo.combustionFol())

    return correctTransferOutForRestart(runInfo, lastCombTime)


def restartCombustionDuringPostProcess(runInfo):
    """Completes full iteration after a failure occurring between the
    completion of a combustion simulation the mapping/prep for next simulation.
    Note: Assumes that the job has been checked manually to ensure that
    combustion did actually complete.

    Parameters
    ----------
    runInfo: dict
        Stores simulation state

    Returns
    -------
    bool:
        Flag indicating successful completion full iteration
    """

    IO.writeToStdOutFile('Restarting job during post processing phase {0} of \
combustion portion of iteration {1} at {2} '.format(runInfo['postProcessStep'],
                                                 runInfo.iter(),
                                                 TimeMod.ctime()))

    # list containing post processing steps yet to be completed
    ppSteps = runInfo.getPostProcessStepsToComplete()

    if 'mapping' in ppSteps:
        combustionBCtoCoolantBC(runInfo)
    
    if runInfo.checkErrors():
        IO.writeToStdErrFile('Job being cancelled after mapping from combustion \
to coolant failed')
        return
    
    # check convergence and set value in runInfo
    if 'convergenceCheck' in ppSteps:
        runInfo.setCombConvergence('comb',checkRunConvergence(runInfo,
            'combustion'))
    
    # rename boundary files to use in convergence checking
    if 'boundaryFileRename' in ppSteps:
        renameBoundaryFiles(runInfo,'combustion')


    # Update inputs.in for next iteration
    if 'updateInputs' in ppSteps:
        newEntries = {
            'restart_number': int(1),
            'restart_flag': 1,
            'end_time': runInfo['combStopTime'] + 720.,
            'map_flag': 'OFF'
        }
        changeEntriesInFile('inputs.in', newEntries, runInfo.combustionFol())

    # copy output to save folder
    if 'saveResults' in ppSteps:
        moveResults(runInfo.combustionFol(), runInfo.combStopTime())

    # rename and move restartFiles 
    if 'moveRestartFiles' in ppSteps:
        moveRestartFiles(runInfo.combustionFol())

    if 'clearingFiles' in ppSteps:
        clearStartDoneFiles(runInfo.combustionFol())

    # Check for error during mapping/checking convergence
    if runInfo.ErrorInSimFlag == True:
        IO.writeToStdErrFile('Error in completing combustion step on restart \
during post-processing, cancelling job')
        return False

    # Update runInfo information
    runInfo.nextCombustionCycle()

    # Just in case this was the final combustion cycle, print complete message
    # and return False to ensure that job exits.
    if runInfo.checkJobComplete():
        IO.writeToStdOutFile('\n\nHTC Simulation completed after {0} \
iterations'.format(runInfo.iter()))
        return False

    IO.writeToStdOutFile('Combustion step successfully completed, continuing \
with simulation',2)


    # need to complete full iteration before entering main loop
    coolantSuccess = performCoolantStep(runInfo)
    if coolantSuccess == False or runInfo.ErrorInSimFlag:
        IO.writeToStdErrFile('Error in completing coolant step, cancelling job')
        return False


    # if simulations have converged and no final cycle, we can kill job,
    # so return false if converged
    if runInfo.checkJobComplete():
        IO.writeToStdOutFile('\n\nHTC Simulation completed after ' +
                           str(runInfo['iter']) + ' iterations')
        return False

    return True


def checkCombustionCompleted(combustfol, expectedTime, testTime=False):
    """additional check to ensure that the combustion simulation 
    completed correctly. Checks by comparing time in largest numbered
    restart file to the expected end time. Note: this functions assumes
    that the latest restart file has the most recent time so it will not
    look at time in restart.rst if any numbered restart files exist.

    Parameters
    ----------
    combustfol: str
        Name of folder containing combustion simulation
    expectedTime: float
        Current end of simulation time to compare against
    testTime: bool
        Boolean to call a different function that gets time from a text based
        restart file used for testing rather than the CVG restart file
    Returns
    -------
    bool:
        Flag indicating combustion has completed
    """

    fileNumber, fname = getRecentFile('restart.rst', combustfol)
    if fileNumber == -2:
        IO.writeToStdErrFile('no restart files exist after simulation ended, \
likely caused by setup')
        return False
    
    resName = combustfol + '/' + fname
    if testTime:
        lastTime = getTimeFromRestartFileTest(resName)
    else:
        lastTime = getTimeFromRestartFile(resName)

    tDiff = float(expectedTime) - lastTime

    if abs(tDiff) >= 0.5:
        IO.writeToStdErrFile('Latest restart file has time of {0}, while the \
expected time is {1}'.format(lastTime, expectedTime))
        return False
    return True
