"""File Operation Functions

Functions used for performing file operations including copying, moving
and modifying. Uses os.system to execute bash commands. 

Variables
---------
MapInText (str): Contains text for map.in file in event that mapping is
    used in first iteration.

Methods
-------
createFolder: Checks if folder with given name exists and creates it if it
    does not.
callMoveFile: Moves file to a new location
callCopyFile: Copies file to a new location
removeTimesInTransferOut: removes times in transfer.out that occur after
    restart time when restarting simulation (avoids duplicate writes)
moveResults: Moves results from completed time step to a folder in results
    folder
moveRestartFiles: moves last three restart files from completed simulation
    to restartFiles folder
checkExistingOutputFiles: Checks for existing output files in a given
    folder. Used by initialization functions during restart.
getTimeFromRestartFile: Reads time in a given restart file.
moveSingleRestartFile: Called by moveRestartFiles to find most recent restart
    file in folder and move it to restartFiles folder.
renameRestartFile: Renames given restart file to restart.rst.
getNumberedFiles: Returns a list containing all instances of a file with
    same name, but number appended (to get all CVG files with restart
    numbering appended to them).
getRecentRestartFile: Checks all restart file times and returns name
    of most recent.
clearStartDoneFiles: Removes converge.start and converge.done files
clearErrorFiles: Removes error files generated by slurm/mpi on restart
    after a job has crashed.
getRecentFile: Gets the file in a folder with the highest restart number
    appended to it.
changeEntriesInFile: Changes entries in a CVG input file according to key/
    value pairs in a provided dict. Note: will not work with files such
    as boundary.in that has multiple instances of the same variable names.
ensureCorrectMappingVars: Ensures that dict entries provided to
    changeEntriesInFile are correctly set when using mapping (ensures that
    restart flag is set to zero).
getEntryInFile: Returns value of a variable in a CVG input file. Note:
    will not work with files that have multiple instances of the same
    variable names.
checkDictEntries: Helper function used by changeEntriesInFile. Checks a given
    line in the file being altered to see if variable matches key in 
    dict with update information.
updateSingleBoundary: Helper function for updateBoundaryData that updates
    variables in a single boundary section.
getBoundaryID: Obtains ID of boundary with given name from boundary.in file
updateBoundaryData: Updated boundary.in file according to a dictionary
    provided to function.
checkForBoundaryFiles: checks folders for thermal boundary files and sets
    values in boundary.in appropriately
checkSimComplete: checks folder for converge.done to determine if simulation
    has completed or crashed.
correctTransferOutForRestart: Corrects the transfer.out file to ensure data
    will not be duplicated in the event of a restart.
"""

import h5py as hpy
import numpy as np
import os
from ruamel.yaml import YAML
from . import IO


# text to include in map.in when mapping coolant
# just in case the map.in doesnt exist when simulations are started
MapInText = """
version: 3.0
##!Exported by CONVERGE Studio v3.0 Dec 16 2020 02:52:22
---

cells_map_all_regions:    1
cells:
   -  map_region:
         filename:        restart.rst
         rotation:
            axis:         X
            angle:        0
         manipulations:
            XCEN_X:
               translate: 0
               scale:     1
            XCEN_Y:
               translate: 0
               scale:     1
            XCEN_Z:
               translate: 0
               scale:     1
"""


def createFolder(folName):
    """Checks if folder exists and creates it if it does not
    
    Parameters
    ----------
    folName: str
        Name of folder to create

    """

    if not os.path.exists(folName):
        os.makedirs(folName)


def callMoveFile(oldName, newName):
    """Moves file to new location. Includes checks to avoid errors from
    os.rename
    
    Parameters
    ----------
    oldName: str
        Current name of file
    newName: str
        New name of file
    """

    # first check to see if the files are the same name. Might occur when
    # trying to rename restart file to restart.rst (not sure how os.rename
    # handles trying to rename a file to the same name, so just avoiding
    # all together)
    if oldName == newName:
        return

    # removing existing file with same name (to avoid errors with os.rename)
    if os.path.exists(newName):
        os.remove(newName)

    # checking to ensure file exists
    if not os.path.exists(oldName):
        IO.writeToStdErrFile('\tTrying to move non-existent file {0} to {1}. \
Continuing with simulations without renaming file.',format(oldName, newName))
        return 
    os.rename(oldName, newName)


def callCopyFile(fnameOld, fnameNew):
    """Copies file to new location. Checks first to ensure old and new
    locations are not the same.
    
    Parameters
    ----------
    fnameOld: str
        Current name of file
    fnameNew: str
        New name of file
    """

    if fnameOld == fnameNew:
        return
    copyStr = 'cp ' + fnameOld + ' ' + fnameNew
    os.system(copyStr)


def removeTimesInTransferOut(transName, fol, restartTime):
    """Removes timesteps saved in transfer.out. Needed to ensure restarted
    simulation does not save same timestep 2x when simulation is restarted.
    
    Parameters
    ----------
    transName: str
        Name of transfer#.out file to check
    fol: str
        Name of folder containing transfer.out file
    restartTime: float
        Time above which data should be removed

    Returns
    -------
    bool:
        False if transfer.out file was not found, or if it was deleted
        because all times were > restartTime, otherwise True.
    """

    transFile = fol + '/' + transName

    # if no transfer.out file exists, return
    if not(os.path.exists(transFile)):
        return False

    # uses grep to quickly find all output times and write them to file.
    # Quicker than trying to read file line by line in python.
    grepStr = 'grep -n ' + transFile + ' -e Crank > transferTimes.tmp'
    os.system(grepStr)

    # reads in file
    with open('transferTimes.tmp','r') as fid:
        lines = fid.readlines()

    # check all times to see if they occur after restart time
    # lineToCut is the line of the transfer.out file to cut at.
    lineToCut = -1
    for line in lines:
        time = float(line.split('=')[1].split('(')[0])
        if time > restartTime:
            lineToCut = int(line.split(':')[0])
            break

    # if no times after restart time, return
    if lineToCut == -1:
        return True

    # restart occurring before first output, so just delete file so it 
    # doesnt cause issues when the files are concatenated
    if lineToCut < 10:
        os.system(str('rm ' + transFile))
        return False

    # In situation that restart time is after transfer.out
    # time, remove those times using head (output to temp file and rename)
    headCmdStr = 'head -{0} {1} > transfer.tmp'.format(lineToCut-1,transFile)
    mvCmdStr = 'mv transfer.tmp ' + transFile
    os.system(headCmdStr)
    os.system(mvCmdStr)
    return True


def moveResults(fol, time, runInfo):
    """Creates folder with final CAD of simulation as name and moves 
    results into folder. Will check to see if folder already exists and
    return if it does (in the event that job fails during post-processing
    phase of iteration). If tarballResults = True, will also use tar function
    to create a zipped tarball of results files for previous iteration.
    Current iteration will remain un-tarred for one iteration so that data
    can be easily accessed for observation or run progress.

    Parameters
    ----------
    fol: str
        Name of folder containing results files
    time: float
        Time to use for name of new results folder.
    runInfo: RunInfoClass
        Object containing state of job
    """

    resultsPath = fol + '/results' 

    # create results folder if it doesnt exist
    createFolder(resultsPath)

    timePath = resultsPath + '/' + str(int(time))

    # if path exists this has already been done, so return
    if os.path.exists(timePath):
        return
    
    # create time directory
    createFolder(timePath)
    timePath += '/'
    
    # move .out, .echo, .log, .h5 and out0 files and output folder
    os.system('mv {0}/*.out {1}'.format(fol, timePath))
    os.system('mv {0}/*.echo {1}'.format(fol, timePath))
    os.system('mv {0}/out0 {1}'.format(fol, timePath))
    os.system('mv {0}/*.log {1}'.format(fol, timePath))
    os.system('mv {0}/output {1}'.format(fol, timePath))
    os.system('mv {0}/*.h5 {1}'.format(fol, timePath))

    if runInfo['tarballResults']:
        prevIterTime = str(int(time-720))
        prevTimePath = resultsPath + '/' + prevIterTime
        if os.path.exists(prevTimePath):
            prevTimeTar = prevTimePath + '.tar.gz'
            tarCmd = 'tar --remove-files -czvf {0} {1} >> {2}'.format(
                prevTimeTar, prevTimePath, resultsPath + '/log.tar')
            # Remove previous folder
            os.system(tarCmd)


def moveRestartFiles(fol):
    """Moves restart files to restart folder and copies latest to
    restart.rst. Restart times are assigned in ascending order
    (most recent time is restart0003.rst)

    Parameters
    ----------
    fol: str
        Name of folder containing results files
    """
    
    # first copy most recent restart file to restart.rst
    renameRestartFile(fol)

    restartPath = fol + '/restartFiles' 

    # create restartFiles folder if it doesn't exist
    createFolder(restartPath)

    moveSingleRestartFile(3, fol)
    moveSingleRestartFile(2, fol)
    moveSingleRestartFile(1, fol)


def checkExistingOutputFiles(fol):
    """Checks to see if there are any output files in a given folder
    (Very simple implementation of iterating through all files until
    finding a filename with .out as the extension. Cleaner
    implementation is possible, but not really important)

    Parameters
    ----------
    fol: str
        Name of folder containing results files

    Returns
    -------
    bool:
        True if output files exist in folder, False otherwise.
    """

    files = os.listdir(fol)
    OutFileExists = False
    ind = 0
    while ((ind < len(files)) and (OutFileExists == False)):
        if files[ind][-4:] == ".out":
            OutFileExists = True
        ind += 1
    return OutFileExists


def getTimeFromRestartFile(rstFile):
    """Extracts and returns time from the a restart file with provided
    name.

    Parameters
    ----------
    rstFile: str
        Name of restart file to check time in

    Returns
    -------
    float:
        Time of savepoint in restart file.
    """

    rstFileTmp = hpy.File(rstFile,'r')
    lastTime = rstFileTmp.attrs.get('TIME_STEP')[0]

    return lastTime


def moveSingleRestartFile(newNum, fol):
    """Finds restart#.rst with highest number in fol, renames it to
    fol/restartFiles/reset(newNum).rst. Note: will delete old file
    before moving to avoid issues with os.rename.

    Parameters
    ----------
    newNum: int
        New number to append to restart file name when moving
    fol: str
        Name of folder to check for restart files in
    """
    
    
    newName = fol + '/restartFiles/restart000' + str(int(newNum)) + '.rst'
    fileNumber, oldName = getRecentFile('restart.rst', fol)
    if fileNumber == -2:
        return
    fullOldName = fol + '/' + oldName
    callMoveFile(fullOldName, newName)


def renameRestartFile(fol='./'):
    """Copies restart#.rst to restart.rst to ensure that newest restart
    file is used when restarting simulations or mapping data.

    Parameters
    ----------
    fol: str
        Name of folder to check for restart files in
    """

    latestRst = getRecentRestartFile(fol)
    if latestRst is None:
        return
    elif latestRst == 'restart.rst':
        return

    oldName = fol + '/' + latestRst
    newName = fol + '/restart.rst'    
    callCopyFile(oldName, newName)


def getNumberedFiles(fname, fol='./'):
    """Gets a list of all numbered versions of a file (since CVG will
    append numbers to output from restarts).

    Parameters
    ----------
    fname: str
        Base name of file to check for numbered versions of (i.e. 
        transfer.out will look for all transfer#.out files)
    fol: str
        Folder to search in

    Returns
    -------
    list of str:
        List containing all versions of file in fol, including base file
        name if it exists.
    """

    filesplit = fname.split('.')
    prefix = filesplit[0]
    suffix = filesplit[1]

    lenP = len(prefix)
    lenS = len(suffix)
    files = os.listdir(fol)

    fileMatches = [i[lenP:-(lenS+1)] for i in files
                   if (prefix == i[:lenP] and suffix == i[-lenS:])]
    retVals = []
    fileMatchesSort = np.sort(fileMatches)
    for i in fileMatchesSort:
        if i == '':
            retVals.append(fname)
        else:
            retVals.append(prefix + i + '.' + suffix)

    return retVals


def getRecentRestartFile(fol):
    """Returns the file name of the most recent restart file. Checks
    actual times of restart files rather than the number appended to
    the file name.
    
    Parameters
    ----------
    fol: str
        Folder to search in

    Returns
    -------
    str:
        name of most recent restart file. Note: Only includes restart
        file name and not folder in string.
    """

    restartFiles = getNumberedFiles('restart.rst', fol)

    if len(restartFiles) == 0:
        return None
    elif len(restartFiles) == 1:
        return restartFiles[0]

    latestTime = -100000
    indexLatestTime = -1
    
    for i, rst in enumerate(restartFiles):
        resName = fol + '/' + rst    
        
        if hpy.is_hdf5(resName):
            rstFileTmp = hpy.File(resName,'r')
            rstTime = rstFileTmp.attrs.get('TIME_STEP')[0]
        else:
            with open(resName,'rb') as restartFile:
                firstLine = restartFile.readline()

            rstTime = float(firstLine.split()[0])
        if rstTime > latestTime:
            indexLatestTime = i
            latestTime = rstTime
    
    return restartFiles[indexLatestTime]


def clearStartDoneFiles(fol):
    """Clears unncessary files used by CVG once simulation completes.
    
    Parameters
    ----------
    fol: str
        Folder to remove files from.
    """

    os.system('rm -f {0}/*.done'.format(fol))
    os.system('rm -f {0}/*.start'.format(fol))


def clearErrorFiles(fol):
    """Clears unncessary files generated by mpirun/slurm when simulation
    crashes. Called when restarting a run.
    
    Parameters
    ----------
    fol: str
        Folder to remove files from.
    """

    os.system('rm -f {0}/abort_trace*'.format(fol))
    os.system('rm -f {0}/*.err'.format(fol))


def getRecentFile(fname, fol='./'):
    """Gets filename with largest value appended to it from a specified
    folder in case of restarts, etc (i.e. if provided with transfer.out,
    and transfer3.out exists in folder from a restart, will return
    3, 'transfer3.out'

    Parameters
    ----------
    fname: str
        Base file name to search for.
    fol: str
        Folder check for files in

    Returns
    -------
    int:
        Largest number appended to base name (-2 if base file doesnt
        exist and -1 if only base file exists)
    str:
        Name of file with largest number appended to it. ('' if base
        file doesnt exist and fname if only it exists)
    """

    filesplit = fname.split('.')
    prefix = filesplit[0]
    suffix = filesplit[1]
    lenP = len(prefix)
    lenS = len(suffix)
    files = os.listdir(fol)

    fileMatches = [i[lenP:-(lenS+1)] for i in files
                   if (prefix == i[:lenP] and suffix == i[-lenS:])]
    maxVal = -1000000
    if len(fileMatches) == 0:
        return -2, ''
    
    if len(fileMatches) == 1 and fileMatches[0] == '':
        retVal = prefix + '.' + suffix
        return -1, retVal

    fileMatchesSort = np.sort(fileMatches)
    for i in fileMatchesSort:
        if i == '':
            continue
        if int(i) > maxVal:
            maxVal = int(i)
            retVal = prefix + i + '.' + suffix
    return maxVal, retVal


def changeEntriesInFile(fname, entries, fol='.', **kwargs):
    """Changes values for a given set of entries in a CVG setup file.
    Saves to new file name if provided newName (and/or newFol) as
    kwargs entries. Must be provided a dictionary with keys being the
    entry names to update values of and value being the new value of
    the entry. Note: This function will not work for CVG files using
    subdictionaries with repeated variable names (i.e. boundary.in
    where each boundary has the same set of variable name).

    Parameters
    ----------
    fname: str
        File to update values in Base file name to search for.
    entries: dict
        Entries to update in file. Key/value pair are variable name
        and new value to update to.
    fol: str
        Folder containing file to be updated.

    Optional Parameters
    -------------------
    newName: str
        Name of file updated information should be saved to
    newFol: str
        Name of folder new file should be saved in.
    """

    fileIn = fol + '/' + fname
    newName = kwargs.get('newName', None)
    newFol = kwargs.get('newFol', fol)
    if newName is None:
        fileOut = 'temp.tmp'
    else:
        fileOut = newFol + '/' + newName
    fIn = open(fol + '/' + fname)
    fileData = fIn.readlines()
    
    numEntries = len(entries)
    entriesFound = 0
    
    entries = ensureCorrectMappingVars(entries, fol)

    numEntries = len(entries)

    with open(fileOut, 'w') as fout:
        for line in fileData:
            
            if entriesFound < numEntries:
                if ' ' not in line:
                    fout.write(line)
                    continue
                foundEntry, line = checkDictEntries(line, entries)
                if foundEntry is not None:
                    del entries[foundEntry]  
                    entriesFound += 1
            
            fout.write(line)

    if len(entries) > 0:
        warnMessage = 'Warning: Errors may exist in simulation because the \
following variables to be updated in {0} do not exist: '.format(fileIn)
        for i in entries:
            warnMessage += i + ', '
        IO.writeToStdErrFile(warnMessage[:-2])

    if newName is None:
        callMoveFile(fileOut, fileIn)


def ensureCorrectMappingVars(entries, fol):
    """Ensures correct variables are used when mapping data for new
    simulation (in inputs.in file). Will also create map.in file in fol
    if it does not exist. Function implemented because of change in how
    mapping was performed in CVG between 2.4 and 3.0

    Parameters
    ----------
    entries: dict
        Entries to update in file. Key/value pair are variable name
        and new value to update to.
    fol: str
        Folder to check that map.in file exists in and create it if not

    Returns
    -------
    dict:
        Updated entries dictionary. 
    """

    # Previously used restart_flag = 2 for mapping from restart, now
    # will be using map_flag = MAP, so adding map_flag = 'MAP' to
    # entries dict when restart_flag = 2. Restart_flag = 1 will
    # superseed map_flag, so no need to ensure map_flag = OFF when
    # restarting_simulation
    if 'restart_flag' in entries:
        if entries['restart_flag'] == 2:
            entries['map_flag'] = 'MAP'
            entries['restart_flag'] = 0

    # if map_flag = 'MAP', this ensures that map.in exists and restart_flag
    # is set to correct value (i.e. wont let it = 1, which superseeds mapping)
    if 'map_flag' in entries:
        if entries['map_flag'] == 'MAP':
            # need to ensure that restart_flag = 0 when mapping
            entries['restart_flag'] = 0

            # make sure map.in is in folder as well
            mapFileOut = fol + '/map.in' 
            if not(os.path.exists(mapFileOut)):
                with open(mapFileOut,'w') as mapOut:
                    mapOut.write(MapInText)

    return entries


def getEntryInFile(fname, entry, fol='.'):
    """Reads the value of a variable in a CVG setup file. 
    Note: Will return value of first instance of variable if multiple
    entries exist in file such as in boundary.in.

    Parameters
    ----------
    fname: str
        File to read value from.
    entry: dict
        Entry to read value from in file.
    fol: str
        Folder containing file

    Returns
    -------
    str or None:
        str of value in file or None if variable not found.
    """

    fileIn = fol + '/' + fname
    
    fIn = open(fol + '/' + fname)
    fileData = fIn.readlines()

    versionInfo = fileData[0]
    for line in fileData:
        if ' ' not in line:
            continue

        lineUse = line.split('#')[0].lstrip()
        entrySplit = lineUse.split(':')
        if entrySplit[0].lower() == entry.lower():
            return entrySplit[1]

    return None


def checkDictEntries(line, entries):
    """Checks line to see if it contains variable found in entries.
    If it doesm it will return line with updated value from entries
    dictionary. 

    Parameters
    ----------
    line: str
        Line read from CVG setup file
    entries: dict
        Dictionary containing variables to be updated.

    Returns
    -------
    str or None:
        variable name that was updated or None if no variable was
        changed.
    str:
        line containing data read from CVG file with new value if
        updated, otherwise original line is returned
    """

    if not(' ' in line):
        return None, line

    lineUse = line.lstrip()
    noComments = lineUse.split('#')[0]
    entrySplit = noComments.split(':')
    if len(entrySplit) == 1:
        return None, line

    if entrySplit[1] == '\n':
        return None, line

    for entry in entries:
        if entrySplit[0].lower() == entry.lower():
            valStr = entrySplit[1].lstrip().rstrip()
            line = line.replace(valStr, str(entries[entry]))
            updatedLineSplit = line.split('#')
            if len(updatedLineSplit[0]) < 70:
                gap = ' '*(70 - len(updatedLineSplit))
                line = updatedLineSplit[0] + gap + '#' + updatedLineSplit[1]
            elif len(updatedLineSplit[0]) > 70:
                line = updatedLineSplit[0][:70] + '#' + updatedLineSplit[1]
            return entry, line
                
    return None, line


def updateSingleBoundary(bndIndex, newData, bYaml):
    """Used by updateBoundaryData function below to update data in
    boundary.in for a single boundary

    Parameters
    ----------
    bndIndex: str
        Index in boundary.in YAML object containing boundary to be
        updated
    newData: dict
        Dictionary containing key/value of variable to update and new
        value to updated them to.
    bYaml: ruamel object
        ruamel (yaml) object of data in boundary.in
    """

    for i in newData:
        iSplit = i.split('.')
        yamlEntry = bYaml['boundary_conditions'][bndIndex]['boundary']
        for j in iSplit:
            yamlEntry = yamlEntry[j]

        yamlEntry = newData[i]


def getBoundaryID(bName, fol='.'):
    """Gets the ID for the specified boundary name from boundary.in

    Parameters
    ----------
    bName: str
        Boundary to obtain ID of.
    fol: str
        Folder containing file

    Returns
    -------
    int or None:
        ID of boundary or None if boundary not found.
    """

    yaml = YAML()
    bndName = fol + '/' + 'boundary.in'

    # writing to an initial temporary file, then moving
    # this is to ensure the heading needed by CVG isnt lost
    fid = open(bndName,'r')

    # set the correct yaml formatting
    yaml.indent(mapping=5, sequence=4, offset=3)

    # skip over file heading before passing to ruamel
    fid.readline()
    fid.readline()
    fid.readline()
    fid.readline()

    # read boundary.in yaml data
    bounds = yaml.load(fid)

    # iterate through all boundaries, updating information
    # contained in file with data in boundaries dict
    for i in range(len(bounds['boundary_conditions'])):
        name = bounds['boundary_conditions'][i]['boundary']['name']
        if name == bName:
            return int(bounds['boundary_conditions'][i]['boundary']['id'])
    
    return None


def updateBoundaryData(boundaries, fol='.'):
    """Updates boundary.in entries for CVG simulation 
    (changeEntriesInFile function does not work to modify this file).
    This function uses ruamel to read data in YAML format. boundaries
    variable is a dictionary with the boundary name used as the key and
    a dictionary with keys/values being the variable to update and the
    new values to update them to. For variables found within subdicts,
    the name should include each subdict name separated by a '.'.
    For example, the value of velocity should use velocity.value as the
    variable name (see example below).
 
    boundaries = {
        'inlet': {
            'region': 12,
            'velocity.value': 10.0,
            'turbulence.tke.type': 'Dirichlet',
            'turbulence.tke.value': '1.0'
        },
        'head_coolant_interface': {
            'temperature.value': 'head_coolantTemp.in'
        }
    }

    Parameters
    ----------
    boundaries: dict
        Dictionary containing information to update boundary.in with
    fol: str
        Folder containing boundary.in file to update
    """

    yaml = YAML()
    bndName = fol + '/' + 'boundary.in'

    # writing to an initial temporary file, then moving
    # this is to ensure the heading needed by CVG isnt lost
    tmpName = 'boundaryTmp.in'
    fid = open(bndName,'r')

    # set the correct yaml formatting
    yaml.indent(mapping=5, sequence=4, offset=3)

    # write the correct heading to temporary file while
    # skipping over lines before passing to ruamel
    with open(tmpName,'w') as fout:
        fout.write(fid.readline())
        fout.write(fid.readline())
        fout.write(fid.readline())
        fout.write(fid.readline())

    # read boundary.in yaml data
    bounds = yaml.load(fid)

    # iterate through all boundaries, updating information
    # contained in file with data in boundaries dict
    for i in range(len(bounds['boundary_conditions'])):
        name = bounds['boundary_conditions'][i]['boundary']['name']
        if name in boundaries:
            updateSingleBoundary(i, boundaries[name], bounds)
            del boundaries[name]
            if len(boundaries) == 0:
                break

    if len(boundaries):
        IO.writeToStdErrFile('Warning: {0} boundaries provided to \
updateBoundaryData did not match names in boundary.in'.format(len(boundaries)))
        IO.writeToStdErrFile('These boundaries include: ')
        for i in boundaries:
            IO.writeToStdErrFile('\t{0}'.format(i))

    with open(tmpName,'a') as fout:
        yaml.dump(bounds, fout)

    os.system('mv {0} {1}'.format(tmpName, bndName))


def checkForBoundaryFiles(simType, runInfo):
    """Checks for thermal boundary files generated by mapping and sets
    values in boundary.in to their filename if they exist, or to temp/HTC
    values defined in runInfo (values can be provided in settings.yaml)
    
    Parameters
    ----------
    simType: str
        either 'combustion' or 'coolant' indicating the simulation to update
    runInfo: RunInfoClass
        Run state object
    """
    changeDict = {}
    if simType.lower() == 'combustion':
        fol = runInfo.combustionFol()
        for i in runInfo['boundaries']:
            fName = i + '_spatialTemp.in'
            if os.path.exists(fol+'/'+fName):
                changeDict[i] = {'temperature.reference_temperature': fName}
            else:
                changeDict[i] = {
                    'temperature.reference_temperature': 
                        runInfo['boundaryTemp'],
                    'temperature.htc': runInfo['boundaryHTC']
                }
    else:
        fol = runInfo.coolantFol()
        for i in runInfo['boundaries']:
            fName = i + '_spatialTemp.in'
            if os.path.exists(fol+'/'+fName):
                changeDict[i] = {'temperature.value': fName}
            else:
                changeDict[i] = {
                    'temperature.value': runInfo['boundaryTemp']
                }

    updateBoundaryData(changeDict, fol)


def checkSimComplete(folName):
    """Checks if a simulation is complete using converge.done file.
    Returns true if file exists in folName and false otherwise

    Parameters
    ----------
    folName: str
        Name of folder to check for converge.done in.
    """

    if os.path.exists('{0}/converge.done'.format(folName)):
        return True
    return False



def correctTransferOutForRestart(runInfo, lastCombTime):
    """If transfer#.out file exists, will move data into transfer.out either
    by moving file (when transfer.out doesnt exist) or concatenating file 
    (when transfer.out does exist). This ensures that no more than two
    transfer.out files exist at a time so that combustion boundary mapping
    function can correctly collect necessary data
    Note: in all restart combustion events, transfer#.out should exist, but
    it will not throw error in the event that this error has occurred
    (this should only occur when restarting simulation that failed after
    the coolant step and before the combustion step)

    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing name of combustion folder.
    lastCombTime: float
        Time of latest restart file
    
    Returns
    -------
    bool:
        Bool indicating successfully completed correcting transfer.out file
    """

    transferFiles = getNumberedFiles('transfer.out', runInfo.combustionFol())
    
    if len(transferFiles) == 0:
        return True
    elif len(transferFiles) == 1:
        # if only 1 transfer file exists, only need to move it in event that
        # it is not transfer.out
        if transferFiles[0] != 'transfer.out':
            if(removeTimesInTransferOut(transferFiles[0],
                                        runInfo.combustionFol(),
                                        lastCombTime)):
                transFile = runInfo.combustionFol() + '/' + transferFiles[0]
                newTransFile = runInfo.combustionFol() + '/transfer.out'
                moveStr = 'mv {0} {1}'.format(transFile, newTransFile)
                os.system(moveStr)
        return True

    elif len(transferFiles) == 2:
        
        if 'transfer.out' not in transferFiles:
            IO.writeToStdErrFile('Two transfer.out files with restart numbers \
appended exist in combustion folder, which should not occur.\n Maximum of \
one transfer#.out file (with or without transfer.out) should exist when \
restarting simulation.\nJob will be cancelled. Do not resubmit before \
correcting issue with transfer files')
            return False

        # check to see if 2nd transfer file contains data that needs to be
        # saved using removeTimesInTransferOut(). Function will return true if
        # 2nd file contains data to be appended to transfer.out, which will
        # require using cat to append it (removeTimesInTransferOut will remove
        # any times after latest restart file). If it returns false, 
        # nothing needs to be done (removeTimesInTransferOut will remove 2nd
        # transfer file if it is empty or contains times that are after latest
        # restart file)
        if(removeTimesInTransferOut(transferFiles[1],
                                    runInfo.combustionFol(), lastCombTime)):
            transFile1 = runInfo.combustionFol() + '/transfer.out'
            transFile2 = runInfo.combustionFol() + '/' + transferFiles[1]

            # This bash function will concatenate corrected transfer#.out
            # file onto the end of transfer.out while ignoring the header
            catStr = 'tail -n +2 {0} >> {1}'.format(transFile2, transFile1)
            os.system(catStr)
            os.system('rm {0}'.format(transFile2))

        return True
    else:
        IO.writeToStdErrFile('Two transfer.out files with restart numbers \
appended exist in combustion folder, which should not occur.\n Maximum of \
one transfer#.out file (with or without transfer.out) should exist when \
restarting simulation.\nJob will be cancelled. Do not resubmit before \
correcting issue with transfer files')
        return False
