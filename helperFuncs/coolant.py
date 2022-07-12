"""Functions for performing coolant phase of iteration

Contains all functions related to the coolant phase of the iteration,
including running CVG, mapping boundary data, and checking convergence.

Methods
-------
mapCoolantDataAndCheckConvergence: maps data to combustion simulation,
    and checks for convergence in coolant simulation.
runSim: changes directory to dir containing coolant sim
    and calls actual CVG run function.
performCoolantStep: Calls CVG to run coolant simulation, restarting up to
    maxRestart times after failure.
prepCoolantRestartAfterFailure: Prepares coolant simulation for a restart
    after a job has been restarted.
restartCoolantDuringPostProcess: Finishing coolant post processing when
    job is stopped during this phase
"""

import os
import time as TimeMod
from .fileOps import clearErrorFiles, changeEntriesInFile, getRecentRestartFile
from .fileOps import moveRestartFiles, clearStartDoneFiles, moveResults
from .fileOps import callMoveFile 
from .fileOps import checkForBoundaryFiles, checkSimComplete
from .testing import runTestSimulation
from . import IO# from .IO import IO.writeToStdErrFile, IO.writeToStdOutFile
from .mapping import coolantBCtoCombustionBC, checkRunConvergence
from .mapping import renameBoundaryFiles


def mapCoolantDataAndCheckConvergence(runInfo):
    """Maps boundary data from transfer.out for combustion simulation
    and checks for convergence by comparing with previous boundary
    values
    
    Parameters
    ----------
    runInfo: dict
        Stores simulation state
    """

    IO.writeToStdOutFile('Mapping boundary data from coolant to combustion \
simulation',2)

    # map data from coolant to combustion domain
    runInfo.setPostProcessStep('mapping','coolant')
    coolantBCtoCombustionBC()
    if runInfo.ErrorInSimFlag:
        IO.writeToStdErrFile('Job being cancelled after mapping from coolant to \
combustion failed')
        return
    
    # check convergence
    runInfo.setPostProcessStep('convergenceCheck','coolant')
    IO.writeToStdOutFile('Checking convergence of coolant simulation',2)
    runInfo['coolCvg'] = checkRunConvergence(runInfo, 'coolant')
    
    # rename boundary files to use in convergence checking
    runInfo.setPostProcessStep('boundaryFileRename','coolant')
    IO.writeToStdOutFile('Renaming files containing newest bounday data from \
coolant simulation',2)
    renameBoundaryFiles(runInfo,'coolant')


def runSim(runInfo):
    """Runs a converge simulation in the coolant directory stored
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
        runTestSimulation(runInfo.coolantFol(), runInfo)
        return

    os.chdir(runInfo.coolantFol())
    runCmd = runInfo.runCmd()
    os.system(runCmd)
    os.chdir('..')


def performCoolantStep(runInfo):
    """Runs coolant simulation, and calls appropriate functions for
    mapping boundaries, checking convergence, saving results/restart
    files, and preparing simulation for next iteration
    
    Parameters
    ----------
    runInfo: dict
        Stores simulation state

    Returns
    -------
    float:
        Time elapsed during simulation.
    bool:
        Flag indicating if simulation was successful (used when restarting)
    """

    IO.writeToStdOutFile('Starting Coolant Step at ' + TimeMod.ctime(),1)

    checkForBoundaryFiles('coolant', runInfo)

    # if restarting job, need to keep previous retry number, so we will zero
    # it out at end of step rather than at beginning. And the input files will
    # have been updated at end of previous iteration (or by the restart
    # function if restarting)
    timeStart = TimeMod.time()
    while(True):
        runInfo['coolIter'] += 1
        # write out run info with nonzero coolIter info in case of restart
        runInfo.write()

        runSim(runInfo)

        if runInfo['ignoreCoolRestart'] == True:
            os.system('rm {0}/restart.rst'.format(runInfo.coolantFol()))
            runInfo['ignoreCoolRestart'] = False

        if checkSimComplete(runInfo.coolantFol()):
            break

        IO.writeToStdOutFile('Coolant simulation did not complete on \
iteration ' + str(runInfo['coolIter']) + ', restarting simulation from last \
savepoint',2)
        
        # remove any error files that might exist after failed simulation
        clearErrorFiles(runInfo.coolantFol())

        if runInfo['coolIter'] > runInfo['maxRestarts']:
            IO.writeToStdErrFile('Job being cancelled after coolant simulation \
has failed {0} consecutive times'.format(runInfo['maxRestarts']))
            runInfo.setSimError()
            return False

        prepRestartFlag = prepCoolantRestartAfterFailure()

        if prepRestartFlag == False:
            IO.writeToStdErrFile('Job being cancelled after error restarting \
coolant simulation')
            runInfo.setSimError()
            return False

    coolantRunTime = TimeMod.time() - timeStart

    IO.writeToStdOutFile('Coolant Step Completed successfully in {0} \
hours'.format(coolantRunTime/3600.),2)

    # map boundarys and check convergence
    mapCoolantDataAndCheckConvergence()

    # Update inputs.in for next iteration. (will be mapping from restart file 
    # in next iteration)
    runInfo.setPostProcessStep('updateInputs','coolant')
    newEntries = {
        'restart_number': int(1),
        'restart_flag': 0,
        'map_flag': 'MAP'
    }
    changeEntriesInFile('inputs.in', newEntries, runInfo.coolantFol())

    # copy output to save folder (combustion stop time was increased by
    # 720 after combustion simulation finished, so need to subtract 720)
    runInfo.setPostProcessStep('saveResults','coolant')
    if runInfo['saveCoolantOutput']:
        IO.writeToStdOutFile('Saving coolant output',2)
        moveResults(runInfo.coolantFol(), runInfo.combStopTime()-720., runInfo)
    else:
        IO.writeToStdOutFile('Removing previous coolant output',2)
        os.chdir(runInfo.coolantFol())
        os.system('rm -rf *.log *.out out0 output *.h5')
        os.chdir('..')

    # rename and move restartFiles (keeping all in event that they are 
    # corrupted. Files will overwrite ones saved after previous iteration)
    runInfo.setPostProcessStep('moveRestartFiles','coolant')
    IO.writeToStdOutFile('Moving restart files for coolant simulation',2)
    moveRestartFiles(runInfo.coolantFol())

    runInfo.setPostProcessStep('clearingFiles','coolant')
    clearStartDoneFiles(runInfo.coolantFol())

    # Update runInfo information and write runInfo
    runInfo.nextCoolantCycle()

    return True


def prepCoolantRestartAfterFailure(runInfo):
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

    latestRst = getRecentRestartFile(runInfo.coolantFol())
    
    # coolant simulation will always generate a restart file at beginning of
    # run, if it doesn't, this indicates there is a problem in the simulation
    # setup
    if latestRst is None:
        # no existing restart file for combustion simulation. 
        IO.writeToStdErrFile('coolant simulation failed before generating a \
restart file. Simulation cannot be restarted.\nCancelling job.')
        return False

    # if latest restart file is not restart.rst, rename it
    if latestRst != 'restart.rst':
        oldName = runInfo.coolantFol() + '/' + latestRst
        newName = runInfo.coolantFol() + '/restart.rst'    
        callMoveFile(oldName, newName)
    
    IO.writeToStdOutFile('Re-starting coolant simulation for attempt ' +
                      str(runInfo['coolIter']+1),2)

    # since coolant is using mapping for initialization, the first 
    # iteration will not be appending the restart number to output files.
    # Therefore, we can use runInfo['coolIter'] as the restart number.
    # We also need to ensure that the map_flag is set to OFF and restart
    # flag is set to 1 when restarting.

    # restart_flag will always be set to 1 here just to ensure that its
    # set correctly before re-running simulation
    newEntries = {
        'restart_number': int(runInfo['coolIter']),
         'restart_flag': 1
    }
    changeEntriesInFile('inputs.in', newEntries, runInfo.coolantFol())

    return True


def restartCoolantDuringPostProcess(runInfo):
    """Completes coolant step after failure during post processing phase.
    Note: Implementation does not track each step of post processing phase
    individually, so errors could result of restarting during the post
    processing phase. Due to the small fraction of time spent in this phase
    compared to the actual simulation phases, its highly unlikely that 
    a simulation will need to restart here.

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
coolant portion of iteration {1} at {2} '.format(runInfo['postProcessStep'],
                                                 runInfo.iter(),
                                                 TimeMod.ctime()))

    # list containing post processing steps yet to be completed
    ppSteps = runInfo.getPostProcessStepsToComplete()


    if 'mapping' in ppSteps:
        coolantBCtoCombustionBC()
    
    if runInfo.ErrorInSimFlag:
        IO.writeToStdErrFile('Job being cancelled after mapping from coolant to \
combustion failed during post-process restart')
        return False
    
    # check convergence
    if 'convergenceCheck' in ppSteps:
        runInfo['coolCvg'] = checkRunConvergence(runInfo, 'coolant')
    
    # rename boundary files to use in convergence checking
    if 'boundaryFileRename' in ppSteps:
        renameBoundaryFiles(runInfo,'coolant')

    # Update inputs.in for next iteration. (will be mapping from restart
    # file in next iteration)
    if 'updateInputs' in ppSteps:
        newEntries = {
            'restart_number': int(1),
            'restart_flag': 0,
            'map_flag': 'MAP'
        }
        changeEntriesInFile('inputs.in', newEntries, runInfo.coolantFol())

    if 'saveResults' in ppSteps:
        if runInfo['saveCoolantOutput']:
            moveResults(runInfo.coolantFol(), runInfo.combStopTime()-720.)
        else:
            os.chdir(runInfo.coolantFol())
            os.system('rm -rf *.log *.out out0 output *.h5')
            os.chdir('..')

    if 'moveRestartFiles' in ppSteps:
        moveRestartFiles(runInfo.coolantFol())
        clearStartDoneFiles(runInfo.coolantFol())


    if runInfo.ErrorInSimFlag == True:
        IO.writeToStdErrFile('Error in completing coolant step on restart at \
post processing phase. Cancelling job')
        return False

    # Update runInfo information and write runInfo
    runInfo.nextCoolantCycle()

    IO.writeToStdOutFile('Post-processing phase for coolant simulation completed \
for iteration {0}. Continuing with next iteration.'.format(runInfo.iter()),2)
    return True
