"""This module defines the common interface for arbitrary waveform generators.

Classes:
    - AWG: Common AWG interface.
    - DummyAWG: A software stub implementation of the AWG interface.
    - ProgramOverwriteException
    - OutOfWaveformMemoryException
"""

from abc import abstractmethod
from numbers import Real
from typing import Set, Tuple, Callable, Optional, Mapping, Sequence, List
from collections import OrderedDict

from qupulse.hardware.util import get_sample_times
from qupulse.utils.types import ChannelID
from qupulse._program._loop import Loop
from qupulse._program.waveforms import Waveform
from qupulse.comparable import Comparable
from qupulse._program.instructions import InstructionSequence
from qupulse.utils.types import TimeType

import numpy

__all__ = ["AWG", "Program", "ProgramOverwriteException",
           "OutOfWaveformMemoryException", "AWGAmplitudeOffsetHandling"]

Program = InstructionSequence


class AWGAmplitudeOffsetHandling:
    IGNORE_OFFSET = 'ignore_offset'   # Offset is ignored.
    CONSIDER_OFFSET = 'consider_offset' # Offset is discounted from the waveforms.
    # TODO OPTIMIZED = 'optimized' # Offset and amplitude are set depending on the waveforms to maximize the waveforms resolution

    _valid = [IGNORE_OFFSET, CONSIDER_OFFSET]


class AWG(Comparable):
    """An arbitrary waveform generator abstraction class.

    It represents a set of channels that have to have(hardware enforced) the same:
        -control flow
        -sample rate

    It keeps track of the AWG state and manages waveforms and programs on the hardware.
    """

    def __init__(self, identifier: str):
        self._identifier = identifier
        self._amplitude_offset_handling = AWGAmplitudeOffsetHandling.IGNORE_OFFSET

    @property
    def identifier(self) -> str:
        return self._identifier

    @property
    def amplitude_offset_handling(self) -> str:
        return self._amplitude_offset_handling

    @amplitude_offset_handling.setter
    def amplitude_offset_handling(self, value):
        """
        value (str): See possible values at `AWGAmplitudeOffsetHandling`
        """
        if value not in AWGAmplitudeOffsetHandling._valid:
            raise ValueError('"{}" is invalid as AWGAmplitudeOffsetHandling'.format(value))

        self._amplitude_offset_handling = value

    @property
    @abstractmethod
    def num_channels(self):
        """Number of channels"""

    @property
    @abstractmethod
    def num_markers(self):
        """Number of marker channels"""

    @abstractmethod
    def upload(self, name: str,
               program: Loop,
               channels: Tuple[Optional[ChannelID], ...],
               markers: Tuple[Optional[ChannelID], ...],
               voltage_transformation: Tuple[Optional[Callable], ...],
               force: bool=False) -> None:
        """Upload a program to the AWG.

        Physically uploads all waveforms required by the program - excluding those already present -
        to the device and sets up playback sequences accordingly.
        This method should be cheap for program already on the device and can therefore be used
        for syncing. Programs that are uploaded should be fast(~1 sec) to arm.

        Args:
            name: A name for the program on the AWG.
            program: The program (a sequence of instructions) to upload.
            channels: Tuple of length num_channels that ChannelIDs of  in the program to use. Position in the list corresponds to the AWG channel
            markers: List of channels in the program to use. Position in the List in the list corresponds to the AWG channel
            voltage_transformation: transformations applied to the waveforms extracted rom the program. Position
            in the list corresponds to the AWG channel
            force: If a different sequence is already present with the same name, it is
                overwritten if force is set to True. (default = False)
        """

    @abstractmethod
    def remove(self, name: str) -> None:
        """Remove a program from the AWG.

        Also discards all waveforms referenced only by the program identified by name.

        Args:
            name: The name of the program to remove.
        """

    @abstractmethod
    def clear(self) -> None:
        """Removes all programs and waveforms from the AWG.

        Caution: This affects all programs and waveforms on the AWG, not only those uploaded using qupulse!
        """

    @abstractmethod
    def arm(self, name: Optional[str]) -> None:
        """Load the program 'name' and arm the device for running it. If name is None the awg will "dearm" its current
        program."""

    @property
    @abstractmethod
    def programs(self) -> Set[str]:
        """The set of program names that can currently be executed on the hardware AWG."""

    @property
    @abstractmethod
    def sample_rate(self) -> float:
        """The sample rate of the AWG."""

    @property
    def compare_key(self) -> int:
        """Comparison and hashing is based on the id of the AWG so different devices with the same properties
        are ot equal"""
        return id(self)

    @abstractmethod
    def set_volatile_parameters(self, program_name: str, parameters: Mapping[str, Real]):
        """Set the values of parameters which were marked as volatile on program creation."""

    def __copy__(self) -> None:
        raise NotImplementedError()

    def __deepcopy__(self, memodict={}) -> None:
        raise NotImplementedError()


class ProgramOverwriteException(Exception):

    def __init__(self, name) -> None:
        super().__init__()
        self.name = name

    def __str__(self) -> str:
        return "A program with the given name '{}' is already present on the device." \
               " Use force to overwrite.".format(self.name)


class ProgramEntry:
    """This is a helper class for implementing awgs drivers. A driver can subclass it to help organizing sampled
    waveforms"""
    def __init__(self, loop: Loop,
                 channels: Tuple[Optional[ChannelID], ...],
                 markers: Tuple[Optional[ChannelID], ...],
                 amplitudes: Tuple[float, ...],
                 offsets: Tuple[float, ...],
                 voltage_transformations: Tuple[Optional[Callable], ...],
                 sample_rate: TimeType,
                 waveforms: Sequence[Waveform] = None):
        """

        Args:
            loop:
            channels:
            markers:
            amplitudes:
            offsets:
            voltage_transformations:
            sample_rate:
            waveforms: These waveforms are sampled and stored in _waveforms. If None the waveforms are extracted from
            loop
        """
        assert len(channels) == len(amplitudes) == len(offsets) == len(voltage_transformations)

        self._channels = tuple(channels)
        self._markers = tuple(markers)
        self._amplitudes = tuple(amplitudes)
        self._offsets = tuple(offsets)
        self._voltage_transformations = tuple(voltage_transformations)

        self._sample_rate = sample_rate

        self._loop = loop

        if waveforms is None:
            waveforms = OrderedDict((node.waveform, None)
                                    for node in loop.get_depth_first_iterator() if node.is_leaf()).keys()

        self._waveforms = OrderedDict(zip(waveforms, self._sample_waveforms(waveforms)))

    def _sample_waveforms(self, waveforms: Sequence[Waveform]):  # -> List[Tuple[numpy.ndarray, ...], Tuple[numpy.ndarray]]:
        sampled_waveforms = []

        time_array, segment_lengths = get_sample_times(waveforms, self._sample_rate)
        for waveform, segment_length in zip(waveforms, segment_lengths):
            wf_time = time_array[:segment_length]

            sampled_channels = []
            for channel, trafo, amplitude, offset in zip(self._channels, self._voltage_transformations,
                                                         self._amplitudes, self._offsets):
                if channel is None:
                    sampled_channels.append(None)
                else:
                    sampled = waveform.get_sampled(channel, wf_time)
                    if trafo:
                        sampled = trafo(sampled)
                    sampled = sampled - offset
                    sampled /= amplitude
                    sampled_channels.append(waveform.get_sampled(channel, wf_time))

            sampled_markers = []
            for marker in self._markers:
                if marker is None:
                    sampled_markers.append(None)
                else:
                    sampled_markers.append(waveform.get_sampled(marker, wf_time) != 0)

            sampled_waveforms.append((tuple(sampled_channels), tuple(sampled_markers)))
        return sampled_waveforms


class OutOfWaveformMemoryException(Exception):

    def __str__(self) -> str:
        return "Out of memory error adding waveform to waveform memory."


class ChannelNotFoundException(Exception):
    def __init__(self, channel):
        self.channel = channel

    def __str__(self) -> str:
        return 'Marker or channel not found: {}'.format(self.channel)
