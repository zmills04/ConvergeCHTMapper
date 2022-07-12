""" Input/Output functions

This file contains functions for reading run information and settings,
writing stdout and stderror messages, and a class to store run
information and setting for use in the current job.

Classes
-------
runInfoClass: holds run information and settings and read/writes to file 

Variables
---------
runInfoDefault (dict): default values for run information variables
settingsDefault (dict): default values for settings variables

Methods
-------
writeToStdErrFile: writes to stderr file
writeToStdOutFile: writes to stdout file
createStdErrFile: creates stderr file
createStdOutFile: creates stdout file
createStdOutFiles: creates both stderr and stdout files
"""

import os
from ruamel.yaml import YAML
from .defaultValues import *
from . import fileOps


# Contains data relevant to running simulations along with settings
# read from runSettings.txt. Will be continually written to file to
# ensure needed information is retained between restarts
runInfoDefault = {
    'iter': 0,
    'combCvg': False,
    'coolCvg': False,
    'combStopTime': None,#StartCAD+720,
    'coolIter': 0,
    'combIter': 0,
    'ignoreCoolRestart': False,
    'ignoreCombRestart': False,
    'finalCombustionCompleted': False,
    'finalCombustionRunning': False,
    'hasFinalCombustionStep': False,
    'postProcessStep': 'none'
}

settingsDefault = {
    'fluxTol': fluxTolDefault,
    'boundaryTempTol': boundaryTempTolDefault,
    'htcTol': htcTolDefault,
    'fluidTempTol': fluidTempTolDefault,
    'boundaryTemp': boundaryTempDefault,
    'boundaryHTC': boundaryHTCDefault,
    'combustionFolder': combustionFolderDefault,
    'coolantFolder': coolantFolderDefault,
    'maxRestarts': maxRestartsDefault,
    'tarballResults': tarballResultsDefault,
    'startTime': None,
    'mapSurfaceFile': None,
    'saveCoolantOutput': saveCoolantOutputDefault,
    'boundaries': [],
    'final_CFL_Files': [],
    'final_twrite_post': None,
    'finalCycleVars': {}
}



class RunInfoClass(dict):
    """
    A class for storing run settings and the current state of the simulation.
    Inherits from dict allowing variables to be accessed like those in 
    a dictionary. Includes functions to load both settings (i.e. convergence
    criteria, boundaries to map, etc) and run information (iterations,
    convergence information, current combustion stop time, etc). Also
    has multiple convenience functions to access commonly used variables.

    Attributes
    ----------
    See __init__ function below and default settings and runInformation
    dictionaries above for variables contained in this class  

    Methods
    -------
    see Below
    """

    def __init__(self, rInfo='htcRunInfo.yaml',settings='settings.yaml'):
        """Initializes class by reading variables from htcRunInfo and settings
        files. Uses default values for any variable not included in files.
        
        Parameters
        ----------
        rInfo: str
            yaml file with run information
        settings: str
            yaml file with settings
        """
        
        self.runInfoFile = rInfo
        self.settingsFile = settings
        self.testFlag = False

        # Initialize error flags (loading flag is for errors loading files,
        # sim flag is set whenever an error occurs during a run)
        self.ErrorLoadingFlag = False
        self.ErrorInSimFlag = False

        # First checking if rInfo file exists. If it does, we will assume that
        # this is a restarted job when creating stdout/stderr files, otherwise
        # we assume its a new job. This really only effects whether the stderr
        # file prints a warning message about creating a new file when
        # restarting 
        if(os.path.exists(rInfo)):
            self.runInfoFound = True
            createStdOutFiles(True)
        else:
            self.runInfoFound = False
            createStdOutFiles(False)

        # load settings file
        if os.path.exists(settings):
            self.loadSettings()
        else:
            writeToStdErrFile('Error: Settings file, {0} does not exist. \
This file is needed to obtain list of boundaries to map thermal data between \
simulations'.format(settings))
            self.ErrorLoadingFlag = True
            return

        # load run info
        if(self.runInfoFound):
            self.loadRunInfo()
        else:
            self.loadDefaultRunInfo()

        # if new simulation, need start time to set initial stop time
        self.getStartTime()

        # Check that run commands have been provided and set from defaults if
        # not
        self.loadRunCmdSettings()


    def getStartTime(self):
        """If new simulation is being started, the stop time of the first 
        cycle is needed, so if its not provided in settings.yaml, it will
        need to be read from inputs.in"""

        # not needed if combStopTime is already known
        if self.__getitem__('combStopTime') is not None:
            return

        if self.__getitem__('startTime') is None:
            startTimeIn = fileOps.getEntryInFile('inputs.in', 'start_time',
                                         self.combustionFol())
            self.__setitem__('startTime',int(startTimeIn))
        stopTimeTmp = self.__getitem__('startTime')+720
        self.__setitem__('combStopTime', stopTimeTmp)


    def loadRunInfo(self):
        """Reads run info from file and sets variables
        """
        
        yaml = YAML()
        settings = yaml.load(open(self.runInfoFile,'r'))
        for i in settings:
            self.__setitem__(i,settings[i])

        # Set unknown values to default
        self.loadDefaultRunInfo()


    def loadDefaultRunInfo(self):
        """runInfoDefault includes defaults values for all variables, so this
        function iterates through the keys and sets any unset variables
        to the default value given in runInfoDefault.
        """

        # Load default runInfo for any variables not loaded from file
        for i in runInfoDefault:
            if i not in list(self.keys()):
                self.__setitem__(i,runInfoDefault[i])

        # Ensure that all runInfo variables loaded are the correct type to
        # avoid future errors that might arise
        for i in runInfoDefault:
            varType = type(runInfoDefault[i])
            if varType is type(None):
                continue
            if not(isinstance(self.__getitem__(i),varType)):
                proType = type(self.__getitem__(i))
                try:
                    newVar = varType(self.__getitem__(i))
                    self.__setitem__(i,newVar)
                except:
                    writeToStdErrFile('Error: Value for runInfo variable {0} \
is wrong type. Provided {1}, needs to be {2}'.format(i,proType,varType))
                    self.ErrorLoadingFlag = True


    def loadRunCmdSettings(self):
        """Checks if variables defining bash command to run simulations were
        provided in settings.yaml and if not, uses defaults. Defaults assume
        that the run command is defined as an environment variable, SLURM
        is the workload manager and mpirun submits jobs. User needs to set
        these in settings.yaml if wanting to use different configurations.
        """
        if 'CMD' not in self.keys():
            cmdVar = os.environ.get('CMD',None)
            if cmdVar is None:
                self.ErrorLoadingFlag = True
                writeToStdErrFile('Error: No run command provided in \
settings.yaml or defined as an environment variable')
                return
            self.__setitem__('CMD',cmdVar)

        if 'mpiExe' not in self.keys():
            self.__setitem__('mpiExe','mpirun')

        if 'nProcs' not in self.keys():
            nProcs = os.environ.get('SLURM_NTASKS', None)
            if nProcs is None:
                self.ErrorLoadingFlag = True
                writeToStdErrFile('Error: runHTC was unable to determine \
number of processors to run on from environment variable.\nnProcs must be \
defined in settings.yaml')
            self.__setitem__('nProcs',os.environ.get('SLURM_NTASKS', None))
            return

        if 'mpiOptions' not in self.keys():
            nProcs = self.__getitem__('nProcs')
            self.__setitem__('mpiOptions', '-np {0}'.format(int(nProcs)))


    def loadSettings(self):
        """Reads run info from file and sets variables. This file is
        must be provided for every job and contain atleast the list of
        boundaries to be mapped as the variable 'boundaries'
        """

        yaml = YAML()
        settings = yaml.load(open(self.settingsFile,'r'))
        for i in settings:
            if i == 'finalCycleVars':
                valToSet = dict(settings[i])
            else:
                valToSet = settings[i]
            self.__setitem__(i,valToSet)

        # Set variables not provided in file to their default values
        self.loadDefaultSettings()


    def loadDefaultSettings(self):
        """settingsDefault includes defaults values for all variables, so this
        function iterates through the keys and sets any unset variables
        to the default value given in settingsDefault.
        """

        # Load default settings for any variables not loaded from file
        for i in settingsDefault:
            if i not in list(self.keys()):
                self.__setitem__(i,settingsDefault[i])

        # check run directory for final_CFL_Files and add them to the list
        finalCFLNames = ['max_cfl_u.final', 'max_cfl_nu.final',
                         'max_cfl_mach.final']
        for i in finalCFLNames:
            if os.path.exists(i):
                self.__getitem__('final_CFL_Files').append(i)

        # If run folder contains max_cfl final files, a specified output step
        # time, or variables to change in final combustion cycle, 
        # hasFinalCombustionStep will be set to True to run an additional
        # simulation with those settings after convergence 
        if (len(self.__getitem__('final_CFL_Files')) > 0 or
            self.__getitem__('final_twrite_post') is not None or
            len(self.__getitem__('finalCycleVars')) > 0):
            self.__setitem__('hasFinalCombustionStep',True)


        self.checkSettingsForErrors()


    def checkSettingsForErrors(self):
        """Checks settings read from file for errors and make appropriate
        changes if possible."""

        # Ensure that all settings variable are the correct type to
        # avoid future errors that might arise. Any defaults that are
        # None will be ignored
        for i in settingsDefault:
            varType = type(settingsDefault[i])
            if varType is type(None):
                continue
            if not(isinstance(self.__getitem__(i),varType)):
                proType = type(self.__getitem__(i))
                try:
                    newVar = varType(self.__getitem__(i))
                    self.__setitem__(i,newVar)
                except:
                    writeToStdErrFile('Error: Value for settings variable {0} \
is wrong type. Provided {1}, needs to be {2}'.format(i,proType,varType))
                    self.ErrorLoadingFlag = True

        # final_twrite_post can either be a float/int with the step size
        # or a filename of a file to be copied into combustion folder
        twritePost = self.__getitem__('final_twrite_post')
        if isinstance(twritePost,str):
            # First make sure its not a string of a int or float.
            if twritePost.isdigit(twritePost):
                self.__setitem__('final_twrite_post', int(twritePost))
            elif twritePost.replace('.','').isdigit(twritePost):
                self.__setitem__('final_twrite_post', float(twritePost))
            else:
                if not(os.path.exists(twritePost)):
                    writeToStdErrFile('Error: Filename given for \
final_twrite_post does not exist in run folder. Please correct and restart \
simulation')
                    self.ErrorLoadingFlag()

        if isinstance(self.__getitem__('boundaries'),str):
            self.__setitem__('boundaries',
                             list(self.__getitem__('boundaries')))


        # ensure that boundary variable is a list
        if isinstance(self.__getitem__('boundaries'),str):
            self.__setitem__('boundaries',
                             list(self.__getitem__('boundaries')))

        # ensure than at least one boundary was provided
        if len(self.__getitem__('boundaries')) == 0:
            writeToStdErrFile('Error: No boundaries names provided for mapping\
 to be performed on. A list of boundaries must be provided in the settings \
for the mapping to work')
            self.ErrorLoadingFlag = True

        # ensure that the name of the surface.dat file for mapping is provided
        # and the file exists
        surfFile = self.__getitem__('mapSurfaceFile')

        if surfFile is None:
            writeToStdErrFile('Error: mapSurfaceFile not defined in \
settings.yaml. The name of the surface file to be used for mapping must be \
provided in settings.yaml using the variable mapSurfaceFile.')
            self.ErrorLoadingFlag = True
        elif not(isinstance(surfFile,str)):
            writeToStdErrFile('Error: Value for mapSurfaceFile provided in \
settings.yaml is not a string. This variable should define the name of the \
mapping surface.dat file')
            self.ErrorLoadingFlag = True
        elif not(os.path.exists(surfFile)):
            writeToStdErrFile('Error: Name provided for mapping surface, {0}, \
(mapSurfaceFile in settings.yaml) does not exist. Please check file \
exists and is named correctly')
            self.ErrorLoadingFlag = True
        

    def checkErrors(self):
        """Convenience function that returns True if any errors have occurred
        and False otherwise.
        """

        return self.ErrorInSimFlag or self.ErrorLoadingFlag


    def setSimError(self):
        """Convenience function that sets run error flag to True
        """

        self.ErrorInSimFlag = True


    def checkJobComplete(self):
        """Convenience function that if final cycle was completed when running
        an additional combustion cycle with different settings. Otherwise it
        returns checkConvergence()"""

        if self.__getitem__('hasFinalCombustionStep'):
            combFl = self.__getitem__('combCvg')
            coolFl = self.__getitem__('coolCvg')
            finalFl = self.__getitem__('finalCombustionCompleted')

            writeToStdOutFile('Checking for completion: Combustion = {0}, \
Coolant = {1}, finalCycle = {2}'.format(combFl, coolFl, finalFl))

            if finalFl:
                writeToStdOutFile('Final combustion cycle completed')
                return True
            return False
        else:
            return self.checkConvergence()


    def nextCoolantCycle(self):
        """Updates variables after successful completion of coolant simulation
        in an iteration. Increments iter, checks for convergence and
        initializes final combustion step if true, resets coolant iterations"""

        self.__setitem__('coolIter',0)
        if self.checkConvergence():
            # If using final cycle, get simulation ready
            if self.__getitem__('hasFinalCombustionStep'):
                writeToStdOutFile('Simulations have converged, starting final \
cycle of combustion')
                self.initializeFinalCombustionRun()
            # if no final combustion, nothing else to do, so return
            else:
                # change postProcessStep to none and write to file
                self.setPostProcessStep('none')
                return

        # increment iteration number and write runInfo
        self.__setitem__('iter',self.__getitem__('iter')+1)
                
        # change postProcessStep to none and write to file
        self.setPostProcessStep('none')


    def nextCombustionCycle(self):
        """Updates variables after successful completion of combustion
        simulation of an iteration. Resets combIter, checks for convergence and
        initializes final combustion step if true, updates combustion stop time
        and updates finalCombustionCompleted if in final iteration"""
        self.__setitem__('combIter',0)
        
        # check if final combustion cycle. If so, set finalCombustionCompleted
        # to True, since calling this function when finalCombustionRunning
        # is True indicates that the last cycle has been finished 
        if self.__getitem__('finalCombustionRunning'):
            self.__setitem__('finalCombustionCompleted',True)
            self.__setitem__('finalCombustionRunning',False)
            # change postProcessStep to none and write to file
            self.setPostProcessStep('none')
            return

        # check for convergence in both simulations. If True, either run is
        # finished (no final cycle) or next cycle is the final one
        if self.checkConvergence():
            # If using final cycle, get simulation ready
            if self.__getitem__('hasFinalCombustionStep'):
                writeToStdOutFile('Simulations have converged, starting final \
cycle of combustion')
                self.initializeFinalCombustionRun()
            # if no final combustion, nothing else to do, so return
            else:
                # change postProcessStep to none and write to file
                self.setPostProcessStep('none')
                return

        # update stop time if another cycle will be run
        cmbStop = self.__getitem__('combStopTime')
        self.__setitem__('combStopTime',cmbStop+720.)

        # change postProcessStep to none and write to file
        self.setPostProcessStep('none')



    def initializeFinalCombustionRun(self):
        """Sets up combustion simulation for final cycle by setting variables 
        in inputs.in, moving appropriate files and saving old versions of files
        just so they are not lost."""

        updateDict = {}
        fileOps.createFolder('OriginalFiles')
        for fname in self.__getitem__('final_CFL_Files'):
            newName = fname.replace('final','in')
            updateDict[fname.replace('.final','')] = newName
            newSaveName = self.combustionFol() + '/' + newName
            oldSaveName = 'OriginalFiles/' + newName
            fileOps.callMoveFile(newSaveName, oldSaveName)
            fileOps.callMoveFile(fname, newSaveName)


        twrite = self.__getitem__('final_twrite_post')
        if twrite is not None:
            updateDict['twrite_post'] = twrite
            if isinstance(twrite,str):
                newName = self.combustionFol() + '/' + twrite
                if os.path.exists(newName):
                    oldSaveName = 'OriginalFiles/' + twrite
                    fileOps.callMoveFile(newName, oldSaveName)
                fileOps.callMoveFile(twrite, newName)

        fileOps.changeEntriesInFile('inputs.in', updateDict, self.combustionFol())
        # Other settings such as updating time, restart number etc will be
        # handled by combustion iteration function like in other iterations

        self.__setitem__('finalCombustionRunning', True)


    def checkConvergence(self):
        """Convenience function that returns True if both simulations have
        converged and False otherwise.
        """
        writeToStdOutFile('\tChecking for convergence: Combustion = {0}, \
Coolant = {1}'.format(self.__getitem__('combCvg'), 
                      self.__getitem__('coolCvg')))
        return (self.__getitem__('combCvg') and
                self.__getitem__('coolCvg'))


    def runCmd(self):
        """Generates the command to run converge simulation based on 
        settings variables.
        """

        retVal = self.__getitem__('mpiExe') + ' '
        retVal += self.__getitem__('mpiOptions') + ' '
        retVal += self.__getitem__('CMD')
        return retVal


    def getPostProcessStepsToComplete(self):
        """Generates a list of post processing steps that still need to be
        completed when restarting after run ends during post processing phase
        """

        ppStepFull = self.__getitem__('postProcessStep')
        if ppStepFull == 'none':
            return []

        ppStep = ppStepFull.split('_')[0]
        
        ppSteps = ['mapping','convergenceCheck','boundaryFileRename',
                   'updateInputs','saveResults','moveRestartFiles',
                   'clearingFiles']
        
        ppInd = ppSteps.index(ppStep)
        return ppSteps[ppInd:]


    def restartAtPostProcess(self):
        """Returns True if this restart is occurring in the middle of the
        post processing phase, otherwise, False.
        """
        
        if self.__getitem__('postProcessStep') == 'none':
            return False
        else:
            return True


    def getPostProcessRunType(self):
        """Returns the run Type that the restart is occurring during when job
        was killed during the post processing phase. Returns an empty string
        if not restarting during a post process.
        """

        if self.__getitem__('postProcessStep') == 'none':
            return ''
        else:
            return self.__getitem__('postProcessStep').split('_')[1]


    def setPostProcessStep(self, ppStep, runType='none'):
        """Sets postProcessStep variable to appropriate value indicating 
        current portion of postprocessing phase after each simulation. This
        will be used if job ends during this phase of cycle. This variable
        set to 'none' by nextCombustionCycle and nextCoolantCycle. Note that 
        this is a string 'none' and not a type None, which ensures variable 
        will always be a string."""

        if ppStep == 'none':
            self.__setitem__('postProcessStep', ppStep)
            return

        ppSteps = ['mapping','convergenceCheck','boundaryFileRename',
                   'updateInputs','saveResults','moveRestartFiles',
                   'clearingFiles']

        if ppStep not in ppSteps:
            writeToStdErrFile('Error: Trying to use non-existent postProcess \
step name {0}. The post process step names include:'.format(ppStep))
            for i in ppSteps:
                writeToStdErrFile('\t{0}'.format(i))
            self.setSimError()

        if 'cool' in runType:
            ppStep += '_coolant'
        else:
            ppStep += '_combustion'

        self.__setitem__('postProcessStep', ppStep)
        self.write()


    def setTesting(self):
        """Sets flag that indicates tests are being run.
        """

        self.testFlag = True


    def testing(self):
        """Returns flag indicating if currently running in test mode
        """

        return self.testFlag

    def iter(self):
        """Convenience function that returns the current job iteration.
        """

        return self.__getitem__('iter')


    def setCombConvergence(self,conv_):
        """Sets combustion convergence boolean.

        Parameters
        ----------
        conv_: bool
            Boolean with True if combustion simulation is converged,
            False otherwise
        """

        self.__setitem__('combCvg', conv_)


    def setCoolConvergence(self,conv_):
        """Sets coolant convergence boolean.

        Parameters
        ----------
        conv_: bool
            Boolean with True if coolant simulation is converged,
            False otherwise
        """
        
        self.__setitem__('coolCvg', conv_)


    def setConvergence(self,rtype,conv_):
        """Sets either convergence boolean.

        Parameters
        ----------
        rtype: str
            String containing 'comb' or 'combustion' if setting boolean
            for combustion simulation and 'cool' or 'coolant' if for
            coolant boolean
        conv_: bool
            Boolean with True if simulation is converged, False otherwise
        """

        if 'comb' in rtype.lower():
            self.__setitem__('combCvg', conv_)
        elif 'cool' in rtype.lower():
            self.__setitem__('coolCvg', conv_)
        else:
            raise Exception('Name of simulation provided to setConvergence \
function in runInfoClass must either be combustion or coolant')


    def combIter(self):
        """Convenience function that returns the current iteration for
        the combustion solver step.
        """

        return self.__getitem__('combIter')


    def coolIter(self):
        """Convenience function that returns the current iteration for
        the coolant solver step.
        """

        return self.__getitem__('coolIter')

    def combStopTime(self):
        """Convenience function that returns the stop time for the current
        combustion simulation.
        """

        return self.__getitem__('combStopTime')

    def combCurrentStartTime(self):
        """Convenience function that returns the start time for the current
        combustion simulation.
        """

        return self.__getitem__('combStopTime') - 720.

    def boundary(self, ind):
        """Convenience function that returns the name of the boundary at index
        ind.
        """

        return (self.__getitem__('boundaries'))[ind]


    def nBoundaries(self):
        """Convenience function that returns the name of the boundary at index
        ind.
        """

        return len(self.__getitem__('boundaries'))

    def combustionFol(self):
        """Convenience function that returns the name of the combustion
        folder.
        """

        return self.__getitem__('combustionFolder')


    def coolantFol(self):
        """Convenience function that returns the name of the coolant
        folder.
        """

        return self.__getitem__('coolantFolder')


    def nBoundaries(self):
        """Convenience function that returns the total number of boundaries.
        """

        return len(self.__getitem__('boundaries'))

    def write(self):
        """Writes the current runInformation to the htcRunInfo.yaml file.
        """

        yaml = YAML()
        outDict = {}
        for i in runInfoDefault:
            outDict[i] = self.__getitem__(i)

        with open(self.runInfoFile,'w') as fout:
            yaml.dump(outDict, fout)


# Appends message to std error file
def writeToStdErrFile(errMessage='',nTabs=0):
    """Writes string to the std error file

    Parameters
    ----------
    errMessage: str
        Message to append to std error file.
    nTabs: int
        Number of tabs to prepend to message
    """

    errMessage = int(nTabs)*'\t' + errMessage

    with open('htcJob.stderr', 'a') as fid:
        fid.write(errMessage + '\n')


# Appends message to std out file
def writeToStdOutFile(outMessage='',nTabs=0):
    """Writes string to the stdout file

    Parameters
    ----------
    errMessage: str
        Message to append to stdout file.
    nTabs: int
        Number of tabs to prepend to message
    """

    outMessage = int(nTabs)*'\t' + outMessage

    with open('htcJob.stdout', 'a') as fid:
        fid.write(outMessage + '\n')


# Creates std error file
def createStdErrFile():
    """Creates a new stderror file and appends run infomation to it.
    """

    jobID = os.environ.get('SLURM_JOB_ID')
    jobName = os.environ.get('SLURM_JOB_NAME')
    if jobName is None:
        jobName = '-1'
    if jobID is None:
        jobID = -1
    with open('htcJob.stderr', 'w') as fid:
        fid.write('Error information from Job: {0} with JobID: {1}\n\n'.format(
            jobName, jobID))


# Creates std out file
def createStdOutFile():
    """Creates a new stdout file and appends run infomation to it.
    """

    jobID = os.environ.get('SLURM_JOB_ID')
    jobName = os.environ.get('SLURM_JOB_NAME')
    if jobName is None:
        jobName = '-1'
    if jobID is None:
        jobID = -1
    with open('htcJob.stdout', 'w') as fid:
        fid.write('Log information from Job: {0} with JobID: {1}\n\n'.format(
            jobName, jobID))


# creates std out and std error files
def createStdOutFiles(restart=False):
    """Creates new stderror and stdout files and prints error message if they
    are created when job is being restarted.

    Parameters
    ----------
    restart: bool
        Bool indicating if this is a restart or new job.
    """

    if restart:
        if(os.path.exists('htcJob.stderr') == False):
            createStdErrFile()
            writeToStdErrFile('Warning: no stderr file existed when \
restarting simulation new htcJob.stderr has been created')
        if(os.path.exists('htcJob.stdout') == False):
            createStdOutFile()
            writeToStdErrFile('Warning: no stdout file existed when \
restarting simulation. New htcJob.stdout has been created')
    else:
        createStdErrFile()
        createStdOutFile()

