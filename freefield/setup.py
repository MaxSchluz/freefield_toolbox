import time
from pathlib import Path
from copy import deepcopy
import collections
import numpy as np
import slab
from sys import platform
from matplotlib import pyplot as plt
from matplotlib.axes import Axes
from freefield import camera
import pandas as pd

if "win" in platform:
    import win32com.client
else:
    print("#######You seem to not be running windows as your OS. Working with"
          "TDT devices is only supported on windows!#######")

# define global variables:
_verbose = True  # determines if feedback is printed out
_speaker_config = None  # either "dome" or "arc"
_calibration_file = None  # file name of the saved calibration filters
_calibration_filter = None  # filters for frequency equalization
_calibration_levels = None  # calibration to equalize levels
_speaker_table = None  # numbers and coordinates of all loudspeakers
_procs = None  # list of active processors
_location = Path(__file__).resolve().parents[0]  # package folder
_samplerate = 48828.125  # default samplerate for generating sounds etc.
_mode = None  # mode at which the setup is currently running
_print_list = []  # last messages printed by the printv function
_rec_tresh = 65  # treshold in dB above which recordings are not rejected
_fix_ele = 0  # fixation points' elevation
_fix_azi = 0  # fixation points' azimuth
_fix_acc = 10  # accuracy for determining if subject looks at fixation point


def initialize_devices(ZBus=False, RX81_file=None, RX82_file=None,
                       RP2_file=None, RX8_file=None, cam=False,
                       connection='GB', mode=None):
    """
    Initialize the different TDT-devices. The input for ZBus and cam is True
    or False, depending on whether you want to use ZBus triggering and the
    cameras or not. The input for the other devices has to be a string with the
    full path to a .rcx file which will be used to initialize the processor.
    Use the argument RX8_file to initialize RX81 and RX82 with the same file.
    Initialzation will take a few seconds per device
    """
    # TODO: set speakers to 0 when intializing setup??
    global _procs
    set_samplerate(_samplerate)
    if not _speaker_config:
        raise ValueError("Please set device to 'arc' or "
                         "'dome' before initialization!")
    printv('Initializing TDT rack.')
    RX81, RX82, RP2, ZB = None, None, None, None
    if mode is not None:
        if ZBus or RX81_file or RX82_file or RX8_file or RP2_file or cam:
            raise ValueError("You cant initialize using a mode and specifying"
                             ".rcx files at the same time!")
        else:
            RX81_file, RX82_file, RP2_file, ZBus, cam = _files_from_mode(mode)
    if RX8_file:  # use this file for both processors
        RX81_file, RX82_file = RX8_file, RX8_file
    if RX81_file:
        RX81 = _initialize_processor(device_type='RX8',
                                     rcx_file=str(RX81_file), index=1,
                                     connection=connection)
    if RX82_file:
        RX82 = _initialize_processor(device_type='RX8',
                                     rcx_file=str(RX82_file), index=2,
                                     connection=connection)
    if RP2_file:
        RP2 = _initialize_processor(device_type='RP2',
                                    rcx_file=str(RP2_file), index=1,
                                    connection=connection)
    if ZBus:
        ZB = _initialize_processor(device_type='ZBus')
    if cam:
        camera.init()
    proc_tuple = collections.namedtuple('TDTrack', 'ZBus RX81 RX82 RP2')
    _procs = proc_tuple(ZBus=ZB, RX81=RX81, RX82=RX82, RP2=RP2)


def _initialize_processor(device_type=None, rcx_file=None, index=1,
                          connection='GB'):
    if device_type.lower() == 'zbus':
        try:
            ZB = win32com.client.Dispatch('ZBUS.x')
        except win32com.client.pythoncom.com_error as err:
            raise ValueError(err)
        if ZB.ConnectZBUS(connection):
            printv('Connected to ZBUS.')
        else:
            raise ConnectionError('Failed to connect to ZBUS.')
        return ZB
    else:  # it's an RP2 or RX8
        try:  # load RPco.x
            RP = win32com.client.Dispatch('RPco.X')
        except win32com.client.pythoncom.com_error as err:
            raise ValueError(err)
        if device_type == "RP2":
            if RP.ConnectRP2(connection, index):  # connect to device
                printv("Connected to RP2")
            else:
                raise ConnectionError('Failed to connect to RP2.')
        elif device_type == "RX8":
            if RP.ConnectRX8(connection, index):  # connect to device
                printv("Connected to RX8")
            else:
                raise ConnectionError('Failed to connect to RX8.')
        else:
            raise ValueError('Unknown device type!')
        if not RP.ClearCOF():
            raise ValueError('ClearCOF failed')
        if not rcx_file[-4:] == '.rcx':
            rcx_file += '.rcx'
        if RP.LoadCOF(rcx_file):
            printv(f'Circuit {rcx_file} loaded.')
        else:
            raise ValueError(f'Failed to load {rcx_file}.')
        if RP.Run():
            printv('Circuit running')
        else:
            raise ValueError(f'Failed to run {rcx_file}.')
        return RP


def _files_from_mode(mode):
    global _mode
    if mode == "play_and_record":
        RP2_file = _location.parents[0]/"rcx"/Path("rec_buf.rcx")
        RX81_file = _location.parents[0]/"rcx"/Path("play_buf.rcx")
        RX82_file = _location.parents[0]/"rcx"/Path("play_buf.rcx")
        ZBus, cam = True, False
        _mode = "play_and_record"
    elif mode == "localization_test":
        RP2_file = _location.parents[0] / Path("rcx/button.rcx")
        RX81_file = _location.parents[0]/"rcx"/Path("play_buf.rcx")
        RX82_file = _location.parents[0]/"rcx"/Path("play_buf.rcx")
        ZBus, cam = True, True
        _mode = "localization_test"
    elif mode == "camera_calibration":
        RP2_file = _location.parents[0] / Path("rcx/button.rcx")
        RX81_file = _location.parents[0] / Path("rcx/leds.rcx")
        RX82_file = _location.parents[0] / Path("rcx/leds.rcx")
        ZBus, cam = True, True
        _mode = "camera_calibration"
    elif mode == "binaural_recording":
        RP2_file = _location.parents[0]/"rcx"/Path("bi_rec_buf.rcx")
        RX81_file = _location.parents[0]/"rcx"/Path("play_buf.rcx")
        RX82_file = _location.parents[0]/"rcx"/Path("play_buf.rcx")
        _mode = "binaural_recording"
        ZBus, cam = True, False
    else:
        raise ValueError("mode % s is not a valid input! Options are: \n"
                         "play_and_record, localization_test, \n"
                         "camera_calibration, binaural_recording" % (mode))
    printv("Setting mode to %s" % (mode))
    return RX81_file, RX82_file, RP2_file, ZBus, cam


def halt():
    'Halt all processors in the rack (all elements that have a Halt method).'
    for proc_name in _procs._fields:
        proc = getattr(_procs, proc_name)
        if hasattr(proc, 'Halt'):
            printv(f'Halting {proc_name}.')
            proc.Halt()
    if camera._cam_type is not None:
        camera.halt()


def set_speaker_config(setup='arc'):
    'Set the freefield setup to use (arc or dome).'
    global _speaker_config, _calibration_filter,\
        _speaker_table, _calibration_file
    if setup == 'arc':
        _speaker_config = 'arc'
        _calibration_file = _location / Path('calibration_filter_arc.npy')
        table_file = _location / Path('speakertable_arc.txt')
    elif setup == 'dome':
        _speaker_config = 'dome'
        _calibration_file = _location / Path('calibration_filter_dome.npy')
        table_file = _location / Path('speakertable_dome.txt')
    else:
        raise ValueError("Unknown device! Use 'arc' or 'dome'.")
    printv(f'Speaker configuration set to {setup}.')
    # lambdas provide default values of 0 if azi or ele are not in the file
    _speaker_table = np.loadtxt(fname=table_file, delimiter=',', skiprows=1,
                                converters={3: lambda s: float(s or 0),
                                            4: lambda s: float(s or 0)})
    idx = np.where(_speaker_table == -999.)
    _speaker_table[idx[0], idx[1]] = None  # change the placeholder -999 to NaN
    printv('Speaker table loaded.')
    if _calibration_file.exists():
        _calibration_filter = slab.Filter.load(_calibration_file)
        printv('Calibration filters loaded.')
    else:
        printv('Setup not calibrated.')


def set_variable(variable, value, proc='RX8s'):
    '''
        Set a variable on a processor to a value. Setting will silently fail if
        variable does not exist in the rcx file. The function will use
        SetTagVal or WriteTagV correctly, depending on whether
        len(value) == 1 or is > 1. proc can be
        'RP2', 'RX81', 'RX82', 'RX8s', or "all", or the index of the device
        in _procs (0 = RP2, 1 = RX81, 2 = RX82), or a list of indices.
        'RX8s' sends the value to all RX8 processors.
        Example:
        set_variable('stimdur', 90, proc='RX8s')
        '''
    if isinstance(proc, str):
        if proc == "all":
            proc = [_procs._fields.index('RX81'), _procs._fields.index(
                'RX82'), _procs._fields.index('RP2')]
        elif proc == 'RX8s':
            proc = [_procs._fields.index('RX81'), _procs._fields.index('RX82')]
        else:
            proc = [_procs._fields.index(proc)]
    elif isinstance(proc, int) or isinstance(proc, float):
        proc = [int(proc)]
    elif isinstance(proc, list):
        if not isinstance(all(proc), int):
            raise ValueError("proc must be either a string, an integer or a"
                             "list of integers!")
    else:
        raise ValueError("proc must be either a string, an integer or a "
                         "list of integers!")

    for p in proc:
        if isinstance(value, (list, np.ndarray)):
            flag = _procs[p]._oleobj_.InvokeTypes(
                15, 0x0, 1, (3, 0), ((8, 0), (3, 0), (0x2005, 0)),
                variable, 0, value)
            printv(f'Set {variable} on {_procs._fields[p]}.')
        else:
            flag = _procs[p].SetTagVal(variable, value)
            printv(f'Set {variable} to {value} on {_procs._fields[p]}.')
    if flag == 0:
        printv("Unable to set tag '%s' to value %s on device %s"
               % (variable, value, proc))


def set_samplerate(x):
    global _samplerate
    _samplerate = x
    slab.Signal.set_default_samplerate(x)
    printv("Setting the default samplerate for generating sounds,"
           "filters etc. to %s Hz" % (x))


def get_variable(variable=None, n_samples=1, proc='RX81', supress_print=False):
    '''
        Get the value of a variable from a processor. Returns None if variable
        does not exist in the rco file. proc can be 'RP2', 'RX81', 'RX82', or
        the index of the device in _procs (0 = RP2, 1 = RX81, 2 = RX82).
        Example:
        get_variable('playing', proc='RX81')
        '''
    if isinstance(proc, str):
        proc = _procs._fields.index(proc)
    if n_samples > 1:
        value = np.asarray(_procs[proc].ReadTagV(variable, 0, n_samples))
        # if value == 0:
        # printv(f'{variable} from {_procs._fields[proc]} returned 0 \n'
        # 'this is probably an error...')
    else:
        value = _procs[proc].GetTagVal(variable)
    if not supress_print:
        printv(f'Got {variable} from {_procs._fields[proc]}.')
    return value


def trigger(trig='zBusA', proc=None):
    '''
        Send a trigger. Options are SoftTrig numbers, "zBusA" or "zBusB".
        For using the software trigger a processor must be specified by name
        or index in _procs. Initialize the zBus befor sending zBus triggers.
        '''
    if isinstance(trig, (int, float)):
        if not proc:
            raise ValueError('Proc needs to be specified for SoftTrig!')
        if isinstance(proc, str):
            proc = _procs._fields.index(proc)  # name to index
        _procs[proc].SoftTrg(trig)
        printv(f'SoftTrig {trig} sent to {_procs._fields[proc]}.')
    elif 'zbus' in trig.lower():
        if not _procs.ZBus:
            raise ValueError('ZBus needs to be initialized first!')
        if trig.lower() == "zbusa":
            _procs.ZBus.zBusTrigA(0, 0, 20)
            printv('zBusA trigger sent.')
        elif trig.lower() == "zbusb":
            _procs.ZBus.zBusTrigB(0, 0, 20)

    else:
        raise ValueError("Unknown trigger type! Must be 'soft', "
                         "'zBusA' or 'zBusB'!")


def wait_to_finish_playing(proc='RX8s', tagname="playback"):
    '''
    Busy wait as long as sound is played from the processors. The .rcx file
    must contain a tag (default name is playback) that has the value 1 while
    sound is being played and 0 otherwise.
        '''
    if proc == 'RX8s':
        proc = ['RX81', 'RX82']
    elif proc == 'all':
        proc = ['RX81', 'RX82', 'RP2']
    else:
        proc = [proc]
    printv(f'Waiting for {tagname} on {proc}.')
    while any(get_variable(variable=tagname, n_samples=1, proc=processor,
                           supress_print=True) for processor in proc):
        time.sleep(0.01)
    printv('Done waiting.')


def speaker_from_direction(azimuth=0, elevation=0):
    '''
        Returns the speaker, channel, and RX8 index that the speaker
        at a given azimuth and elevation is attached to.
        '''
    row = int(np.argwhere(np.logical_and(
        _speaker_table[:, 3] == azimuth, _speaker_table[:, 4] == elevation)))
    speaker = int(_speaker_table[row, 0])
    channel = int(_speaker_table[row, 1])
    rx8 = int(_speaker_table[row, 2])
    return speaker, channel, rx8, azimuth, elevation


def speaker_from_number(speaker):
    '''
        Returns the channel, RX8 index, azimuth, and elevation
        that the speaker with a given number (1-48) is attached to.
        '''
    row = int(np.argwhere(_speaker_table[:, 0] == speaker))
    channel = int(_speaker_table[row, 1])
    rx8 = int(_speaker_table[row, 2])
    azimuth = _speaker_table[row, 3]
    elevation = _speaker_table[row, 4]
    return speaker, channel, rx8, azimuth, elevation


def speakers_from_list(speakers):
    """
    Get a subset of speakers from a list that contains either speaker numbers
    of tuples with (azimuth, elevation) of each speaker
    """
    if not isinstance(speakers, list):
        raise ValueError("speakers mut be a list!")
    if all(isinstance(x, int) for x in speakers):
        speaker_list = [speaker_from_number(x) for x in speakers]

    elif all(isinstance(x, tuple) for x in speakers):
        speaker_list = \
            [speaker_from_direction(x[0], x[1]) for x in speakers]
    else:
        raise ValueError("the list of speakers must contain either \n"
                         "integers (speaker numbers) or \n"
                         "tuples (azimuth and elevation)")
    return speaker_list


def all_leds():
    '''
    Get speaker, RX8 index, and bitmask of all speakers which have a LED
    attached --> won't be necessary once all speakers have LEDs
    '''
    idx = np.where(_speaker_table[:, 5] == _speaker_table[:, 5])[0]
    return _speaker_table[idx]


def shift_setup(delta_ele=0, delta_azi=0):
    '''
    Shift the whole speaker setup by adding delte_ele and delta_azi to the
    coordinates of each speaker. Useful when the listeners position is changed.
    To reverse changes reload the table by calling set_speaker_config.
    '''
    global _speaker_table
    _speaker_table[:, 3] += delta_azi
    _speaker_table[:, 4] += delta_ele
    printv("shifting the loudspeaker array by % s degree in azimuth / n"
           "and % s degree in elevation" % (delta_azi, delta_ele))


def set_signal_and_speaker(signal=None, speaker=0, apply_calibration=True):
    '''
        Upload a signal to the correct RX8 and channel (channel on the other
        RX8 set to -1). If apply_calibration=True, apply the speaker's inverse
        filter before upoading. 'speaker' can be a speaker number (1-48) or
        a tuple (azimuth, elevation).
        '''
    if isinstance(speaker, tuple):
        speaker, channel, proc = \
            speaker_from_direction(azimuth=speaker[0], elevation=speaker[1])
    else:
        speaker, channel, proc, azimuth, elevation = speaker_from_number(speaker)
    if apply_calibration:
        if not _calibration_file.exists():
            raise FileNotFoundError('No calibration file found.'
                                    'Please calibrate the speaker setup.')
        printv('Applying calibration.')
        signal.level *= _calibration_levels[int(speaker)]
        signal = _calibration_filter.channel(int(speaker)).apply(signal)
    set_variable(variable='chan', value=channel, proc=proc)
    set_variable(variable="data", value=signal.data, proc=proc)
    # set the other channel to non existant
    set_variable(variable='chan', value=25, proc=3-proc)


def printv(message):
    """
    Print a message if _verbose is True and the message is not among the
    last 5 printed messages
    """
    # TODO: set different verbosity levels
    global _print_list
    if _verbose and message not in _print_list:
        print(message)
        _print_list.append(message)
        if len(_print_list) > 5:
            _print_list.remove(_print_list[0])


def get_recording_delay(distance=1.6, samplerate=48828.125, play_device=None,
                        rec_device=None):
    """
        Calculate the delay it takes for played sound to be recorded. Depends
        on the distance of the microphone from the speaker and on the devices
        digital-to-analog and analog-to-digital conversion delays.
        """
    n_sound_traveling = int(distance / 343 * samplerate)
    if play_device:
        if play_device == "RX8":
            n_da = 24
        elif play_device == "RP2":
            n_da = 30
        else:
            raise ValueError("Input %s not understood!" % (play_device))
    else:
        n_da = 0
    if rec_device:
        if rec_device == "RX8":
            n_ad = 47
        elif rec_device == "RP2":
            n_ad = 65
        else:
            raise ValueError("Input %s not understood!" % (rec_device))
    else:
        n_ad = 0
    return n_sound_traveling + n_da + n_ad


# functions implementing complete procedures:
def localization_test(sound, speakers, n_reps, n_images=1):
    """
    Run a basic localization test where the same sound is played from different
    speakers in randomized order, without playing the same position twice in
    a row. After every trial the presentation is paused and the listener has
    to localize the sound source by pointing the head towards the source and
    pressing the response button. The cameras need to be calibrated before the
    test! After every trial the listener has to point to the middle speaker at
    0 elevation and azimuth and press the button to iniciate the next trial.
    """
    if not _mode == "localization_test":
        initialize_devices(mode="localization_test")
    if isinstance(sound, slab.sound.Sound) and sound.nchannels == 1:
        data = sound.data.flatten()  # Not sure if flatten is needed...
    elif isinstance(sound, np.ndarray) and sound.ndim == 1:
        data = sound
    else:
        raise ValueError("Sound must be a 1D array or instance of slab.Sound!")
    if camera._cal is None:
        raise ValueError("Camera must be calibrated before localization test!")
    warning = slab.Sound.clicktrain(duration=0.4).data.flatten()
    speakers = speakers_from_list(speakers)
    seq = slab.Trialsequence(speakers, n_reps, kind="non_repeating")
    response = pd.DataFrame(columns=["ele_target", "azi_target", "ele_response", "azi_response"])
    while seq.n_remaining > 0:
        _, ch, proc, azi, ele = seq.__next__()
        trial = {"azi_target": azi, "ele_target": ele}
        set_variable(variable="chan", value=ch, proc="RX8%s" % int(proc))
        set_variable(variable="chan", value=25, proc="RX8%s" % int(3-proc))
        set_variable(variable="playbuflen", value=len(sound), proc="RX8s")
        set_variable(variable="data", value=data, proc="RX8s")
        trigger()
        while not get_variable(variable="response", proc="RP2"):
            time.sleep(0.01)
        ele, azi = camera.get_headpose(n=n_images, convert=True, average=True)
        # TODO: implement success sound?
        trial["azi_response"], trial["ele_response"] = azi, ele
        response = response.append(trial, ignore_index=True)
        head_in_position = 0
        while head_in_position == 0:
            while not get_variable(variable="response", proc="RP2"):
                time.sleep(0.01)
            ele, azi = camera.get_headpose(n=1, convert=True, average=True)
            if ele is np.nan:
                ele = 0
            if azi is np.nan:
                azi = 0
            if np.abs(ele-_fix_ele) < _fix_acc and np.abs(azi-_fix_azi) < _fix_acc:
                head_in_position = 1
            else:
                print(np.abs(ele-_fix_ele), np.abs(azi-_fix_azi))
                set_variable(variable="data", value=warning, proc="RX8s")
                set_variable(variable="chan", value=1, proc="RX81")
                set_variable(variable="chan", value=25, proc="RX82")
                set_variable(variable="playbuflen", value=len(warning), proc="RX8s")
                trigger()
    return response


def equalize_speakers(speakers="all", target_speaker=23, bandwidth=1/10,
                      freq_range=(200, 16000), plot=False, test=True):
    """
    Equalize the loudspeaker array in two steps. First: equalize over all
    level differences by a constant for each speaker. Second: remove spectral
    differeces by inverse filtering.
    """
    global _calibration_filter, _calibration_levels
    import datetime
    printv('Starting calibration.')
    if not _mode == "play_and_record":
        initialize_devices(mode="play_and_record")
    sig = slab.Sound.chirp(duration=0.05, from_freq=50, to_freq=16000)
    if speakers == "all":  # use the whole speaker table
        speaker_list = _speaker_table
    else:  # use a subset of speakers
        speaker_list = speakers_from_list(speakers)
    _calibration_levels = _level_equalization(sig, speaker_list, target_speaker)
    fbank, rec = _frequency_equalization(sig, speaker_list, target_speaker, bandwidth, freq_range)
    if plot:  # save plot for each speaker
        for i in range(rec.nchannels):
            _plot_equalization(target_speaker, rec.channel(i),
                               fbank.channel(i), i)
    if _calibration_file.exists():
        date = datetime.datetime.now().strftime("_%Y-%m-%d-%H-%M-%S")
        rename_previous = \
            _location.parent / Path("log/"+_calibration_file.stem + date
                                    + _calibration_file.suffix)
        _calibration_file.rename(rename_previous)
    fbank.save(_calibration_file)  # save as 'calibration_arc.npy' or dome.
    _calibration_filter = slab.Filter.load(_calibration_file)
    printv('Calibration completed.')
    if test:
        rec, rec_filt = test_equalization(speakers)
        return rec, rec_filt


def _level_equalization(sig, speaker_list, target_speaker):
    """
    Record the signal from each speaker in the list and return the level of each
    speaker relative to the target speaker(target speaker must be in the list)
    """
    rec = []
    for row in speaker_list:
        rec.append(play_and_record(row[0], sig, apply_calibration=False))
        if row[0] == target_speaker:
            target = rec[-1]
    rec = slab.Sound(rec)
    rec.data[:, rec.level < _rec_tresh] = target.data  # thresholding
    return target.level / rec.level


def _frequency_equalization(sig, speaker_list, target_speaker, bandwidth, freq_range):
    """
    play the level-equalized signal, record and compute and a bank of inverse filter
    to equalize each speaker relative to the target one. Return filterbank and recordings
    """
    rec = []
    for row in speaker_list:
        modulated_sig = deepcopy(sig)
        modulated_sig.level *= _calibration_levels[int(row[0])]
        rec.append(play_and_record(row[0], modulated_sig, apply_calibration=False))
        if row[0] == target_speaker:
            target = rec[-1]
    rec = slab.Sound(rec)
    rec.data[:, rec.level < _rec_tresh] = target.data  # thresholding
    fbank = slab.Filter.equalizing_filterbank(target=target, signal=rec, low_lim=freq_range[0],
                                              hi_lim=freq_range[1], bandwidth=bandwidth)
    return fbank, rec


def test_equalization(speakers="all", title=""):
    """
    play chirp with and without the equalization filter and compare the
    results.
    """
    sig = slab.Sound.chirp(duration=0.05, from_freq=50, to_freq=16000)
    rec, rec_filt = [], []
    if speakers == "all":  # use the whole speaker table
        speaker_list = _speaker_table
    else:  # use a subset of speakers
        speaker_list = speakers_from_list(speakers)
    for row in speaker_list:
        rec.append(play_and_record(row[0], sig, apply_calibration=False))
        rec_filt.append(play_and_record(row[0], sig, apply_calibration=True))

    rec_filt = slab.Sound(rec_filt)
    rec = slab.Sound(rec)

    rec.data = rec.data[:, rec.level > _rec_tresh]
    rec_filt.data = rec_filt.data[:, rec_filt.level > _rec_tresh]

    fig, ax = plt.subplots(2, 2, sharex="col", sharey="col")
    fig.suptitle(title)
    spectral_range(rec, plot=ax[0, 0])
    spectral_range(rec_filt, plot=ax[1, 0])
    rec.spectrum(axes=ax[0, 1])
    rec_filt.spectrum(axes=ax[1, 1])
    plt.show()
    return rec, rec_filt


def spectral_range(signal, bandwidth=1/5, low_lim=50, hi_lim=20000, thresh=3,
                   plot=True, log=True):
    """
    Compute the range of differences in power spectrum for all channels in
    the signal. The signal is devided into bands of equivalent rectangular
    bandwidth (ERB - see More&Glasberg 1982) and the level is computed for
    each frequency band and each channel in the recording. To show the range
    of spectral difference across channels the minimum and maximum levels
    across channels are computed. Can be used for example to check the
    effect of loud speaker equalization.
    """
    # generate ERB-spaced filterbank:
    fbank = slab.Filter.cos_filterbank(length=1000, bandwidth=bandwidth,
                                       low_lim=low_lim, hi_lim=hi_lim,
                                       samplerate=signal.samplerate)
    center_freqs, _, _ = slab.Filter._center_freqs(low_lim, hi_lim, bandwidth)
    center_freqs = slab.Filter._erb2freq(center_freqs)
    # create arrays to write data into:
    levels = np.zeros((signal.nchannels, fbank.nchannels))
    max_level, min_level = np.zeros(fbank.nchannels), np.zeros(fbank.nchannels)
    for i in range(signal.nchannels):  # compute ERB levels for each channel
        levels[i] = fbank.apply(signal.channel(i)).level
    for i in range(fbank.nchannels):  # find max and min for each frequency
        max_level[i] = max(levels[:, i])
        min_level[i] = min(levels[:, i])
    difference = max_level-min_level
    if plot is True or isinstance(plot, Axes):
        if isinstance(plot, Axes):
            ax = plot
        else:
            fig, ax = plt.subplots(1)
        # frequencies where the difference exceeds the threshold
        bads = np.where(difference > thresh)[0]
        for y in [max_level, min_level]:
            if log is True:
                ax.semilogx(center_freqs, y, color="black", linestyle="--")
            else:
                ax.plot(center_freqs, y, color="black", linestyle="--")
        for bad in bads:
            ax.fill_between(center_freqs[bad-1:bad+1], max_level[bad-1:bad+1],
                            min_level[bad-1:bad+1], color="red", alpha=.6)
    return difference


def play_and_record(speaker_nr, sig, compensate_delay=True,
                    apply_calibration=False):
    """
    Play the signal from a speaker and return the recording. Delay compensation
    means making the buffer of the recording device n samples longer and then
    throwing the first n samples away when returning the recording so sig and
    rec still have the same legth. For this to work, the circuits rec_buf.rcx
    and play_buf.rcx have to be initialized on RP2 and RX8s and the mic must
    be plugged in.
    Parameters:
        speaker_nr: integer between 1 and 48, index number of the speaker
        sig: instance of slab.Sound, signal that is played from the speaker
        compensate_delay: bool, compensate the delay between play and record
    Returns:
        rec: 1-D array, recorded signal
    """
    # TODO use binaural class for binaural recordings

    if _mode == "binaural_recording":
        binaural = True  # 2 channel recording
    elif _mode == "play_and_record":
        binaural = False  # record single channle
    else:
        raise ValueError("Setup must be initalized in 'play_and_record' for "
                         "single or 'binaural' for two channel recording!"
                         "\n current mode is %s" % (_mode))
    set_variable(variable="playbuflen", value=sig.nsamples, proc="RX8s")
    if compensate_delay:
        n_delay = get_recording_delay(play_device="RX8", rec_device="RP2")
    else:
        n_delay = 0
    set_variable(variable="playbuflen", value=sig.nsamples, proc="RX8s")
    set_variable(variable="playbuflen", value=sig.nsamples+n_delay, proc="RP2")
    set_signal_and_speaker(sig, speaker_nr, apply_calibration)
    trigger()  # start playing and wait
    wait_to_finish_playing(proc="all")
    if binaural is False:
        rec = get_variable(variable='data', proc='RP2',
                           n_samples=sig.nsamples+n_delay)[n_delay:]
    if binaural is True:
        recl = get_variable(variable='datal', proc='RP2',
                            n_samples=sig.nsamples+n_delay)[n_delay:]
        recr = get_variable(variable='datar', proc='RP2',
                            n_samples=sig.nsamples+n_delay)[n_delay:]
        rec = [recl, recr]
    return slab.Sound(rec)  # names for channels?


def _plot_equalization(target, signal, filt, speaker_nr, low_lim=50,
                       hi_lim=20000, bandwidth=1/8):
    """
    Make a plot to show the effect of the equalizing FIR-filter on the
    signal in the time and frequency domain. The plot is saved to the log
    folder (existing plots are overwritten)
    """
    row = speaker_from_number(speaker_nr)  # get the speaker
    signal_filt = filt.apply(signal)  # apply the filter to the signal
    fig, ax = plt.subplots(2, 2, figsize=(16., 8.))
    fig.suptitle("Equalization Speaker Nr. %s at Azimuth: %s and "
                 "Elevation: %s" % (speaker_nr, row[2], row[3]))
    ax[0, 0].set(title="Power per ERB-Subband", ylabel="A")
    ax[0, 1].set(title="Time Series", ylabel="Amplitude in Volts")
    ax[1, 0].set(title="Equalization Filter Transfer Function",
                 xlabel="Frequency in Hz", ylabel="Amplitude in dB")
    ax[1, 1].set(title="Filter Impulse Response",
                 xlabel="Time in ms", ylabel="Amplitude")
    # get level per subband for target, signal and filtered signal
    fbank = slab.Filter.cos_filterbank(
        1000, bandwidth, low_lim, hi_lim, signal.samplerate)
    center_freqs, _, _ = slab.Filter._center_freqs(low_lim, hi_lim, bandwidth)
    center_freqs = slab.Filter._erb2freq(center_freqs)
    for data, name, color in zip([target, signal, signal_filt],
                                 ["target", "signal", "filtered"],
                                 ["red", "blue", "green"]):
        levels = fbank.apply(data).level
        ax[0, 0].plot(center_freqs, levels, label=name, color=color)
        ax[0, 1].plot(data.times*1000, data.data, alpha=0.5, color=color)
    ax[0, 0].legend()
    w, h = filt.tf(plot=False)
    ax[1, 0].semilogx(w, h, c="black")
    ax[1, 1].plot(filt.times, filt.data, c="black")
    fig.savefig(_location.parent/Path("log/speaker_%s_equalization.pdf"
                                      % (speaker_nr)), dpi=800)
    plt.close()
