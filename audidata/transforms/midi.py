import math
import librosa
import numpy as np
from pretty_midi import Note

from audidata.tokenizers.base import BaseTokenizer


class PianoRoll:
    r"""Convert the MIDI note and pedal events a full song into piano rolls of 
    a short clip. The rolls include frame roll, onset roll, offset roll, and
    velocity roll.
    """

    def __init__(
        self, 
        fps: int = 100, 
        pitches_num: int = 128, 
        soft_target: bool = False
    ):
        self.fps = fps
        self.pitches_num = pitches_num
        self.soft_target = soft_target

    def __call__(self, data: dict) -> dict:
        r"""Convert data dict to piano rolls."""

        notes = data["note"]
        pedals = data["pedal"]
        start_time = data["start_time"]
        clip_duration = data["clip_duration"]

        clip_frames = round(self.fps * clip_duration) + 1

        # Rolls
        frame_roll = np.zeros((clip_frames, self.pitches_num), dtype="float32")
        onset_roll = np.zeros((clip_frames, self.pitches_num), dtype="float32")
        offset_roll = np.zeros((clip_frames, self.pitches_num), dtype="float32")
        velocity_roll = np.zeros((clip_frames, self.pitches_num), dtype="float32")

        if self.soft_target:
            soft_onset_roll = np.zeros((clip_frames, self.classes_num), dtype="float32")
            soft_offset_roll = np.zeros((clip_frames, self.classes_num), dtype="float32")

        clip_notes = []

        # Go through all notes
        for note in notes:

            onset_time = note.start - start_time
            offset_time = note.end - start_time
            pitch = note.pitch
            velocity = note.velocity

            if offset_time < 0:
                continue

            elif clip_duration < onset_time < math.inf:
                continue

            if offset_time == onset_time:
                offset_time = onset_time + (1. / fps)

            clip_note = Note(
                pitch=pitch, 
                start=onset_time, 
                end=offset_time, 
                velocity=velocity
            )
            clip_notes.append(clip_note)

            if offset_time < onset_time:
                raise "offset should not be smaller than onset!"

            # Update rolls
            elif onset_time < 0 and 0 <= offset_time <= clip_duration:

                offset_idx = round(offset_time * self.fps)
                offset_roll[offset_idx, pitch] = 1
                frame_roll[0 : offset_idx + 1, pitch] = 1

                if self.soft_target:
                    pass
                    # TODO but not necessary
                    # tmp = np.zeros(clip_frames)
                    # tmp[offset_idx] = 1
                    # delayed_frames = (offset_time * fps) % 1
                    # tmp = fractional_delay(tmp, delayed_frames)
                    # soft_offset_roll[:, pitch] += tmp
                    # from IPython import embed; embed(using=False); os._exit(0)

            elif onset_time < 0 and clip_duration < offset_time < math.inf:

                frame_roll[:, pitch] = 1

            elif 0 <= onset_time <= clip_duration and 0 <= offset_time <= clip_duration:

                onset_idx = round(onset_time * self.fps)
                offset_idx = round(offset_time * self.fps)
                onset_roll[onset_idx, pitch] = 1
                velocity_roll[onset_idx, pitch] = velocity / 128.0
                offset_roll[offset_idx, pitch] = 1
                frame_roll[onset_idx : offset_idx + 1, pitch] = 1

            elif 0 <= onset_time <= clip_duration and clip_duration < offset_time < math.inf:

                onset_idx = round(onset_time * self.fps)
                onset_roll[onset_idx, pitch] = 1
                velocity_roll[onset_idx, pitch] = velocity / 128.0
                frame_roll[onset_idx : , pitch] = 1

            else:
                raise NotImplementedError

        # Sort notes
        clip_notes.sort(key=lambda note: (note.start, note.pitch, note.end, note.velocity))

        data.update({
            "onset_roll": onset_roll,
            "offset_roll": offset_roll,
            "frame_roll": frame_roll,
            "velocity_roll": velocity_roll,
            "clip_note": clip_notes
        })

        return data


class Note2Token:
    r"""Target transform. Transform midi notes to tokens. Users may define their
    own target transforms.
    """

    def __init__(self, 
        tokenizer: BaseTokenizer, 
        max_tokens: int
    ):
        
        self.tokenizer = tokenizer
        self.max_tokens = max_tokens

    def __call__(self, data: dict) -> list[int]:
        
        notes = data["clip_note"]
        clip_duration = data["clip_duration"]

        # Notes to words
        words = ["<sos>"]

        for note in notes:

            onset_time = note.start
            offset_time = note.end
            pitch = note.pitch
            velocity = note.velocity

            if 0 <= onset_time <= clip_duration:

                words.append("name=note_on")
                words.append("time={}".format(onset_time))
                words.append("pitch={}".format(pitch))
                words.append("velocity={}".format(velocity))
                
            if 0 <= offset_time <= clip_duration:

                words.append("name=note_off")
                words.append("time={}".format(offset_time))
                words.append("pitch={}".format(pitch))

        words.append("<sos>")

        # Words to tokens
        tokens = np.array([self.tokenizer.stoi(w) for w in words])
        tokens_num = len(tokens)

        # Masks
        masks = np.ones_like(tokens)

        tokens = librosa.util.fix_length(data=tokens, size=self.max_tokens)
        masks = librosa.util.fix_length(data=masks, size=self.max_tokens)

        data["word"] = words
        data["token"] = tokens
        data["mask"] = masks
        data["tokens_num"] = tokens_num

        return data
