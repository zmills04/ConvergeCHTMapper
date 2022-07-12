"""Functions for initializing runs 

Will determine if its a new simulation, or restart of a previous one from 
htcRunInfo.txt (must exist for a restart) and files in combustion and/or
coolant folders. If it is a restart, either combustion or coolant simulation
will begin from latest restart file. If its not, new simulations will begin.

Methods
-------

"""

import os
# from .combustion import restartCombustionDuringPostProcess
# from .coolant import restartCoolantDuringPostProcess, performCoolantStep
from .fileOps import checkExistingOutputFiles, getRecentRestartFile
from .fileOps import callMoveFile, changeEntriesInFile, getNumberedFiles
from .fileOps import MapInText, getTimeFromRestartFile 
from .fileOps import correctTransferOutForRestart, clearErrorFiles
from . import coolant, combustion
from . import IO
from . import mapping
from .import testing

def checkCurrentState():
    """script checks for current state of simulation when job is launched
    and take appropriate steps based on determined state. One of three
    possible states will be determined using htcRunInfo.yaml.
    These are:
        1) No htcRunInfo.txt: new job, will call initializeJob()
        2) htcRunInfo.txt exists and job has already complete: prints message 
            indicating a job has already completed and exit.
        3) htcRunInfo.txt exists and boundaries have not converged: 
            restart of unfinished job. Will call initializeRestart()
            which will initialize restart appropriately.

    Returns
    -------
    bool:
        Flag indicating successful completion of initialization steps
    runInfoClass:
        Object containing run state and settings.
    """

    runInfo = IO.RunInfoClass()

    # Check that htcRunInfo and settings files loaded correctly
    if runInfo.checkErrors():
        IO.writeToStdErrFile('Error initializing run info. Check \
htcRunInfo.yaml and settings.yaml for errors. Cancelling job')
        return False, runInfo

    # new job
    if runInfo.runInfoFound == False:
        IO.writeToStdOutFile('No htcRunInfo file found, starting new simulation')
        return initializeJob(runInfo), runInfo

    elif runInfo.restartAtPostProcess():
        if runInfo.getPostProcessRunType() == 'coolant':
            return coolant.restartCoolantDuringPostProcess(runInfo), runInfo
        else:
            return combustion.restartCombustionDuringPostProcess(
                runInfo), runInfo

    # If completed job accidently restarted, print message and exit
    elif runInfo.checkJobComplete():
            IO.writeToStdErrFile('Attempting to restart simulation that has \
converged. Current job will be cancelled')
            IO.writeToStdErrFile('If attempting to continue previously converged \
job, change convergence information in htcRunInfo.txt')
            return False, runInfo

    return initializeRestart(runInfo), runInfo


def checkForExistingData(fol):
    """Checks for .out files in fol and any existing files in fol/results
    and fol/restartFiles

    Parameters
    ----------
    fol: str
        Name of folder to search in.

    Returns
    -------
    bool:
        Flag indicating if correction of transfer.out file.
    """

    resultsFolder = fol + '/results'
    restartFolder = fol + '/restartFiles'
    if checkExistingOutputFiles(fol):
        IO.writeToStdErrFile('{0} contains .out files, but a new job is being \
started. Cancelling job.'.format(fol))
        IO.writeToStdErrFile('Delete .out files in ' + fol + ' before \
resubmitting job')
        return True

    if os.path.exists(resultsFolder):
        resultDirs = os.listdir(resultsFolder)
        if len(resultDirs) > 0:
            IO.writeToStdErrFile(fol + ' folder data in results folder, but a \
new job is being started. Cancelling job.')
            IO.writeToStdErrFile('Delete data in ' + resultsFolder + ' before \
resubmitting job')
            return True

    if os.path.exists(restartFolder):
        restartDirs = os.listdir(restartFolder)
        if len(restartDirs) > 0:
            IO.writeToStdErrFile(fol + ' folder data in restartFiles folder, but \
a new job is being started. Cancelling job.')
            IO.writeToStdErrFile('Delete data in ' + restartFolder + ' before \
resubmitting job')
            return True

    return False


def setCombustionToMapValues(runInfo):
    """Finds combustion restart file with highest time and preps simulation
    to use it for mapping when starting a new simulation
    
    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing name of combustion folder.
    """

    # find latest restart file and make sure it is called restart.rst
    latestRst = getRecentRestartFile(runInfo.combustionFol())
    if latestRst != 'restart.rst':
        oldName = runInfo.combustionFol() + '/' + latestRst
        newName = runInfo.combustionFol() + '/restart.rst'    
        callMoveFile(oldName, newName)
    
    newEntries = {
        'restart_number': int(1),
        'restart_flag': 0,
        'end_time': runInfo['combStopTime'],
        'map_flag': 'MAP'
    }
    changeEntriesInFile('inputs.in', newEntries, runInfo.combustionFol())

    if not(os.path.exists(runInfo.combustionFol()+'/map.in')):
        with open(runInfo.combustionFol()+'/map.in','w') as fid:
            fid.write(MapInText)


def setCoolantToMapValues(runInfo):
    """Finds combustion restart file with highest time and preps simulation
    to use it for mapping when starting a new simulation. Since coolant
    simulations are started at t = 0 each time, the highest time might not
    be the most recent restart file. Therefore, make sure that the restart
    file to be used is the only one in the folder when starting job.
    
    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing name of combustion folder.
    """

    # find latest restart file and make sure it is called restart.rst
    latestRst = getRecentRestartFile(runInfo.coolantFol())
    if latestRst != 'restart.rst':
        oldName = runInfo.coolantFol() + '/' + latestRst
        newName = runInfo.coolantFol() + '/restart.rst'    
        callMoveFile(oldName, newName)
    
    newEntries = {'restart_number': int(1), 'restart_flag': 0, 'map_flag': 'MAP'}
    changeEntriesInFile('inputs.in', newEntries, runInfo.coolantFol())

    if not(os.path.exists(runInfo.coolantFol()+'/map.in')):
        with open(runInfo.coolantFol()+'/map.in','w') as fid:
            fid.write(MapInText)


def initializeJob(runInfo):
    """Initializes a new job by making sure all input files setup correctly
    will also check for restart files in combustion/coolant folders and
    will set up simulations to map from these if they exist

    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing name of combustion folder.

    Returns
    -------
    bool:
        Bool indicating successful initialization of simulations
    """

    # generate htc_map.in files for coolant and combustion and make sure
    # that htc_map_64 and surfaceFile exist in run folder.
    mapFilesExist = genMappingFiles(runInfo)
    if mapFilesExist == False:
        IO.writeToStdErrFile('Error with mapping files. Cancelling simulation')
        return False


    # check if data already exists in combustion/coolant folders
    # if so, job will be cancelled to allow for data to be manually deleted
    # before restarting job. This will avoid deleting/overwriting useful
    # data in the even that htcRunInfo was unknowingly deleted or corrupted.
    if (checkForExistingData(runInfo.combustionFol()) or
        checkForExistingData(runInfo.coolantFol())):
        return False

    # check for existing restart file in combustion folder. If one exists,
    # make sure its named restart.rst, set inputs.in variables appropriately
    # and ensure that map.in exists.
    combRestarts = getNumberedFiles('restart.rst', runInfo.combustionFol())
    if len(combRestarts) > 0:
        IO.writeToStdOutFile('Found restart file in combustion folder. \
Initializing combustion simulation with data')
        setCombustionToMapValues(runInfo)
        # when mapping in a new simulation, the time in the data used for 
        # mapping may be higher than the initial stop time. Therefore, we
        # set ignoreCombRestart in runInfo to True to ensure that this is
        # deleted before the next time restart file times are checked.
        runInfo['ignoreCombRestart'] = True
    else:
        newEntries = {
            'restart_number': int(1),
            'restart_flag': 0,
            'end_time': runInfo['combStopTime'],
            'map_flag': 'OFF'
        }

        changeEntriesInFile('inputs.in', newEntries, runInfo.combustionFol())
        IO.writeToStdOutFile('No restart file found in combustion folder. \
Using generic initialization data from initialize.in')

    # check for existing restart file in coolant folder. If one exists, 
    # make sure its named restart.rst, set inputs.in variables appropriately
    # and ensure that map.in exists. 
    coolantRestarts = getNumberedFiles('restart.rst', runInfo.coolantFol())
    if len(coolantRestarts) > 0:
        IO.writeToStdOutFile('Found restart file in coolant folder. Initializing \
coolant simulation with data')
        setCoolantToMapValues()
        runInfo['ignoreCoolRestart'] = True
    else:
        newEntries = {
            'restart_number': int(1),
            'restart_flag': 0,
            'map_flag': 'OFF'
        }
        changeEntriesInFile('inputs.in', newEntries, runInfo.coolantFol())
        IO.writeToStdOutFile('No restart file found in coolant folder. Using \
generic initialization data from initialize.in')


    IO.writeToStdOutFile('New run initialization complete')
    os.system('rm -f log.*')
    return True


def initializeCoolantRestart(runInfo):
    """Will initialize a job for restarting during the coolant simulation 
    phase of the iteration and complete the iteration before returning.

    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing name of combustion folder.

    Returns
    -------
    bool:
        Bool indicating successfully completed initializing and running
        coolant simulation (i.e. finished full iteration)
    """

    IO.writeToStdOutFile('Initializing coolant simulation for restart at \
iteration {0}.'.format(runInfo['iter']))

    # checking to ensure than restart file for combustion simulation still exists
    # before starting simulation. If it doesnt, the job will be cancelled.
    combRestart = runInfo.combustionFol() + '/restart.rst' 
    if not(os.path.exists(combRestart)):
        IO.writeToStdErrFile('No restart.rst file found in combustion folder. \
Restart#.rst file may not have been renamed to restart.rst after combustion \
simulation completed. Cancelling job')
        return False

    # ensure combustion restart is at the correct time
    if runInfo.testing():
        lastCombTime = testing.getTimeFromRestartFileTest(combRestart)
    else:
        lastCombTime = getTimeFromRestartFile(combRestart)

    expectedTime = runInfo['combStopTime'] - 720.
    combTimeDiff = expectedTime - lastCombTime
    if abs(combTimeDiff) > 1:
        IO.writeToStdErrFile('Error in combustion restart file. Time in restart\
\nfile {0} does not match expected value of {1}'.format(lastCombTime, 
                                                      expectedTime))
        IO.writeToStdErrFile('Cancelling job. Check for restart#.rst with \
correct time before restarting job')
        return False


    # checks for latest restart file and copies it to restart.rst if
    # necessary
    latestRst = getRecentRestartFile(runInfo.coolantFol())
    if latestRst is None:
        # no existing restart file. This should only occur when job failed in
        # first iteration after combustion simulation finished, but if it does
        # occur, the simulation will just be initialized by initialize.in
        # values
        newEntries = {
            'restart_number': int(1),
            'restart_flag': 0,
            'map_flag': 'OFF'
        }
    else:
        if latestRst != 'restart.rst':
            oldName = runInfo.coolantFol() + '/' + latestRst
            newName = runInfo.coolantFol() + '/restart.rst'    
            callMoveFile(oldName, newName)
        newEntries = {
            'restart_number': runInfo['coolIter'],
            'restart_flag': 1,
            'map_flag': 'OFF'
        }

    changeEntriesInFile('inputs.in', newEntries, runInfo.coolantFol())
    IO.writeToStdOutFile('Initialization of restart at coolant phase \
successful',1)
    return coolant.performCoolantStep(runInfo)


def initializeCombustionRestart(runInfo):
    """will initialize combustion restart to most recent time, and will
    allow job to continue into main loop where it will start with
    restarted combustion simulation. If transfer#.out file exists, it will
    move data into transfer.out either by copying file (when only numbered 
    transfer file exists) or concatenating file (when transfer.out does 
    exist). This ensures that no more than two transfer.out files exist at a
    time so that combustion boundary mapping function can correctly collect
    necessary data.

    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing name of combustion folder.

    Returns
    -------
    bool:
        Bool indicating successfully completed initializing combustion
        simulation for restart.
    """

    IO.writeToStdOutFile('Restarting simulation at combustion step of \
iteration {0}'.format(runInfo.iter()))

    latestRst = getRecentRestartFile(runInfo.combustionFol())
    
    if latestRst is None:
        # no existing restart file for combustion simulation. 
        IO.writeToStdErrFile('No restart files in combustion folder. Cannot \
restart simulation.\nIf restart file cannot be found, delete htcRunInfo.yaml \
and all output before starting new simulation')
        return False
    
    latestRestartFull = runInfo.combustionFol() + '/' + latestRst

    if runInfo.testing():
        lastCombTime = testing.getTimeFromRestartFileTest(latestRestartFull)
    else:
        lastCombTime = getTimeFromRestartFile(latestRestartFull)

    stopTime = runInfo['combStopTime']
    combTimeDiff = stopTime - lastCombTime
    if combTimeDiff > 721:
        IO.writeToStdErrFile('Most recent restart file is for t = {0}, while \
current combustion simulation should have started at {1}.\nSimulation will be \
allowed to run, but will continue until t = {2}.\nTo reduce the stop time, \
cancel simulation and update htcRunInfo.yaml and inputs.in to desired stop \
time before resubmitting job'.format(lastCombTime, stopTime-720., stopTime))
    elif combTimeDiff < 0:
        IO.writeToStdErrFile('Most recent restart file is for t = {0}, while \
current combustion simulation should have ended at {1}.\nSimulation will be \
cancelled. To restart simulation,\nupdate htcRunInfo.txt and inputs.in to \
correct stop time before resubmitting job'.format(lastCombTime, stopTime))
        return False

    # if latest restart file is not restart.rst, rename it
    if latestRst != 'restart.rst':
        oldName = runInfo.combustionFol() + '/' + latestRst
        newName = runInfo.combustionFol() + '/restart.rst'    
        callMoveFile(oldName, newName)
    
    IO.writeToStdOutFile('Restarting simulation at combustion step of iteration \
{0} with t = {1} and end time of {2}'.format(runInfo.iter(), 
                                             lastCombTime, stopTime))
    
    # update inputs.in with restart_number set to combIter+1 (
    # performCombustionStep will increment value in runInfo before starting
    # simulation, so it shouldnt be incremented here)
    newEntries = {
        'restart_number': runInfo['combIter']+1,
        'restart_flag': 1,
        'map_flag': 'OFF'
    }
    changeEntriesInFile('inputs.in', newEntries, runInfo.combustionFol())

    return correctTransferOutForRestart(runInfo, lastCombTime)


def initializeRestart(runInfo):
    """Initializes a restart job based on data in htcRunInfo.yaml. Will
    determine the appropriate simulation type to start with, which is done
    by checking the combIter and coolIter variables. Whichever one is
    non-zero is the current simulation being run. If restarting in coolant
    simulation, will set inputs.in values and complete simulation before job
    enters main loop. If restarting at combustion simulation, will set 
    inputs.in values, concatenate any data in transfer#.out with data in
    transfer.out if it exists, or move it to transfer.out if it doesn't and
    begin main loop. 

    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing name of combustion folder.

    Returns
    -------
    bool:
        Bool indicating successfully initialized for restart
    """

    # Generate and check for mapping files
    mapFilesExist = genMappingFiles(runInfo)
    if mapFilesExist == False:
        IO.writeToStdErrFile('Error with mapping files. Cancelling simulation')
        return False

    # remove any error files that might exist in combustion and coolant folders
    clearErrorFiles(runInfo.combustionFol())
    clearErrorFiles(runInfo.coolantFol())

    if runInfo['coolIter'] > 0:
        # restarting at coolant simulation. Need to setup and finish coolant
        # simulation step
        return initializeCoolantRestart(runInfo)
    elif runInfo['combIter'] > 0:
        # restarting at combustion simulation. Simulation will continue in
        # main loop
        return initializeCombustionRestart(runInfo)

    # TODO: Set up necessary methods to have job be able to start in between
    # simulations
    IO.writeToStdErrFile('Attempting to restart a simulation that failed outside \
of coolant or combustion simulations.\nDetermine which step was most recently \
performed, set appropriate values to restart from that step in simulation \
and delete most recent restart files before restarting job')

    return False


def genMappingFiles(runInfo):
    """Calls genHTCInputFiles in mapping.py and checks to ensure that
    all files needed for mapping exist. Should be called at initialization
    of new runs and restart runs just to ensure that correct htc_inputs.in
    files are in folder.

    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing name of combustion folder.

    Returns
    -------
    bool:
        Bool indicating successfully generated htc_inputs.in files and 
        all necessary files exist.
    """

    IO.writeToStdOutFile('Generating htc_map.in files for coolant and combustion')
    success = mapping.genHTCInputFiles(runInfo)
    if success == False:
        IO.writeToStdErrFile('Error: Failed to generate htc_inputs.in files for \
each simulation.')
        return False

    return mapping.checkForMappingFiles(runInfo)
    
