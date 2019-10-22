import numpy as np
import sys
sys.path.append("C:/Projects/soundtools")
sys.path.append("C:/Projects/freefield_toolbox")
import slab
from freefield import setup as fs
import os
from scipy import signal
import time
cd = fs._location.parent
rx8_path=os.path.join(cd,"examples", "play_buf.rcx")
rp2_path=os.path.join(cd,"examples", "rec_buf.rcx")

def record_transfer_function(sound="chirp",dur=0.04, n_reps=10, samplerate=48828.125, speakers="all", setup="dome"):
    fs.set_speaker_config(setup)
    fs.initialize_devices(RX81_file=rx8_path, RX82_file=rx8_path, RP2_file=rp2_path, ZBus=True)
    out_path = os.path.join(cd, "transfer_functions", setup)
    if speakers=="all":
        speakers = list(range(1,48))
    if not isinstance(speakers, (list,np.ndarray)):
        raise ValueError("'speakers' must be 'all' or a list/array!")
    else: # speakers is list, continue...
        if sound.lower()=="chirp":
            sound_in = slab.Sound.chirp(duration=dur, samplerate=samplerate)
        elif sound.lower()=="whitenoise":
            sound_in = slab.Sound.whitenoise(duration=dur, samplerate=samplerate)
        elif sound.lower()=="pinknoise":
            sound_in = slab.Sound.pinknoise(duration=dur, samplerate=samplerate)
        else:
            raise ValueError("Unkown sound type!")
        sound_in.level=100
        sound_in.ramp(duration=dur/10, when="both")
        delay_samples = fs.get_recording_delay(da_delay="RX8", ad_delay="RP2")
        fs.set_variable(variable="delay",value=delay_samples, proc="RP2")
        fs.set_variable(variable="playbuflen",value=sound_in.nsamples,proc="RX8s")
        fs.set_variable(variable="data",value=sound_in.data ,proc="RX8s")
        fs.set_variable(variable="recbuflen",value=sound_in.nsamples+delay_samples, proc="RP2")
        for i in speakers:
            fname = "speaker_%s_%sms_%s_tf.wav"%(i,int(dur*1000),sound)
            sound_out = np.zeros((n_reps, sound_in.nsamples))
            channel, rx8, azimuth, elevation = fs.speaker_from_number(i)
            fs.set_variable(variable="chan",value=channel, proc="RX8"+str(rx8))
            time.sleep(0.5)
            for n in range(n_reps):
                fs.trigger()
                while fs.get_variable(variable="recording", proc="RP2"):
                    time.sleep(0.01)
                time.sleep(0.5)
                rec = fs.get_variable(variable="data_ch1",n_samples=sound_in.nsamples+delay_samples, proc="RP2")
                sound_out[n] = rec[delay_samples::]
            sound_out = slab.Sound(data=sound_out, samplerate=samplerate)
            sound_out.write(os.path.join(out_path,fname),normalise=True)
    sound_in.write(os.path.join(out_path,"%sms_%s.wav"%(int(dur*1000),sound)),normalise=True)
    fs.halt()

def impulse_response(played_signal, recorded_signals):

    fs = played_signal.samplerate
    Tr = played_signal.duration
    T = recorded_signals.duration
    x = played_signal.data.flatten()

    for i in range(recorded_signals.nchannels):
        y = recorded_signals[:,i]
        h = 1/len(y) * signal.fftconvolve(y, x[::-1], mode='full')

    plt.figure(figsize=(10, 5))
    t = 1/fs * np.arange(len(h))
    plt.plot(t, h)


    plt.axis([0.0, 1.0, -1.1*np.max(np.abs(h)), 1.1*np.max(np.abs(h))])
    plt.xlabel(r'$t$ in s')
    plt.ylabel(r'$\hat{h}[k]$');