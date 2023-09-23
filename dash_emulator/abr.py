from abc import ABC, abstractmethod
from typing import Dict, Optional
from collections import OrderedDict

from dash_emulator.bandwidth import BandwidthMeter
from dash_emulator.buffer import BufferManager
from dash_emulator.models import AdaptationSet


class ABRController(ABC):
    @abstractmethod
    def update_selection(
        self, adaptation_sets: Dict[int, AdaptationSet]
    ) -> Dict[int, int]:
        """
        Update the representation selections

        Parameters
        ----------
        adaptation_sets: Dict[int, AdaptationSet]
            The adaptation sets information

        Returns
        -------
        selection: Dict[int, int]
            A dictionary where the key is the index of an adaptation set, and
            the value is the chosen representation id for that adaptation set.
        """
        pass


class DashABRController(ABRController):
    def __init__(
        self,
        panic_buffer: float,
        safe_buffer: float,
        bandwidth_meter: BandwidthMeter,
        buffer_manager: BufferManager,
        abr: str,
        max_buffer_duration: float,
    ):
        """
        Parameters
        ----------
        panic_buffer: float
            The bitrate chosen won't go up when the buffer level is lower than panic buffer level
        safe_buffer: float
            The bitrate chosen won't go down when the buffer level is higher than safe buffer level
        bandwidth_meter: BandwidthMeter
            A bandwidth meter which could provide the latest bandwidth estimate
        buffer_manager : BufferManager
            A buffer manager which could provide the buffer level estimate
        """
        self.panic_buffer = panic_buffer
        self.safe_buffer = safe_buffer
        self.buffer_size = max_buffer_duration
        self.bandwidth_meter = bandwidth_meter
        self.buffer_manager = buffer_manager
        self.abr_algorithm = abr

        self.rate_map = None
        self._min_bitrate_representations: Dict[int, int] = {}

        self._last_selections: Optional[Dict[int, int]] = None

        self.RESERVOIR = 0.1
        self.UPPER_RESERVOIR = 0.9

    def update_selection(
        self, adaptation_sets: Dict[int, AdaptationSet]
    ) -> Dict[int, int]:
        if self.abr_algorithm == "buffer-based":
            return self.buffer_based(adaptation_sets)
        elif self.abr_algorithm == "bandwidth-based":
            return self.bandwidth_based(adaptation_sets)
        elif self.abr_algorithm == "hybrid":
            return self.hybrid_based(adaptation_sets)

    def hybrid_based(self, adaptation_sets: Dict[int, AdaptationSet]) -> Dict[int, int]:
        # Only use 70% of measured bandwidth
        available_bandwidth = int(self.bandwidth_meter.bandwidth * 0.7)

        # Count the number of video adaptation sets and audio adaptation sets
        num_videos = 0
        num_audios = 0
        for adaptation_set in adaptation_sets.values():
            if adaptation_set.content_type == "video":
                num_videos += 1
            else:
                num_audios += 1

        # Calculate ideal selections
        if num_videos == 0 or num_audios == 0:
            bw_per_adaptation_set = available_bandwidth / (num_videos + num_audios)
            ideal_selection: Dict[int, int] = dict()

            for adaptation_set in adaptation_sets.values():
                ideal_selection[
                    adaptation_set.id
                ] = self.choose_ideal_selection_bandwidth_based(
                    adaptation_set, bw_per_adaptation_set
                )
        else:
            bw_per_video = (available_bandwidth * 0.8) / num_videos
            bw_per_audio = (available_bandwidth * 0.2) / num_audios
            ideal_selection: Dict[int, int] = dict()
            for adaptation_set in adaptation_sets.values():
                if adaptation_set.content_type == "video":
                    ideal_selection[
                        adaptation_set.id
                    ] = self.choose_ideal_selection_bandwidth_based(
                        adaptation_set, bw_per_video
                    )
                else:
                    ideal_selection[
                        adaptation_set.id
                    ] = self.choose_ideal_selection_bandwidth_based(
                        adaptation_set, bw_per_audio
                    )

        buffer_level = self.buffer_manager.buffer_level
        final_selections = dict()

        # Take the buffer level into considerations

        if self._last_selections is not None:
            for id_, adaptation_set in adaptation_sets.items():
                representations = adaptation_set.representations
                last_repr = representations[self._last_selections.get(id_)]
                ideal_repr = representations[ideal_selection.get(id_)]
                if buffer_level < self.panic_buffer:
                    final_repr_id = (
                        last_repr.id
                        if last_repr.bandwidth < ideal_repr.bandwidth
                        else ideal_repr.id
                    )
                elif buffer_level > self.safe_buffer:
                    final_repr_id = (
                        last_repr.id
                        if last_repr.bandwidth > ideal_repr.bandwidth
                        else ideal_repr.id
                    )
                else:
                    final_repr_id = ideal_repr.id
                final_selections[id_] = final_repr_id
        else:
            final_selections = ideal_selection

        self._last_selections = final_selections
        return final_selections

    def bandwidth_based(
        self, adaptation_sets: Dict[int, AdaptationSet]
    ) -> Dict[int, int]:
        # Only use 70% of measured bandwidth
        # available_bandwidth = int(self.bandwidth_meter.bandwidth * 0.7)
        available_bandwidth = int(self.bandwidth_meter.bandwidth)
        print("\nAvailable bandwidth: ", available_bandwidth)
        # Count the number of video adaptation sets and audio adaptation sets
        num_videos = 0
        num_audios = 0
        for adaptation_set in adaptation_sets.values():
            if adaptation_set.content_type == "video":
                num_videos += 1
            else:
                num_audios += 1

        # Calculate ideal selections
        if num_videos == 0 or num_audios == 0:
            bw_per_adaptation_set = available_bandwidth / (num_videos + num_audios)
            ideal_selection: Dict[int, int] = dict()

            for adaptation_set in adaptation_sets.values():
                ideal_selection[
                    adaptation_set.id
                ] = self.choose_ideal_selection_bandwidth_based(
                    adaptation_set, bw_per_adaptation_set
                )
        else:
            bw_per_video = (available_bandwidth * 0.8) / num_videos
            bw_per_audio = (available_bandwidth * 0.2) / num_audios
            ideal_selection: Dict[int, int] = dict()

            for adaptation_set in adaptation_sets.values():
                if adaptation_set.content_type == "video":
                    ideal_selection[
                        adaptation_set.id
                    ] = self.choose_ideal_selection_bandwidth_based(
                        adaptation_set, bw_per_video
                    )
                else:
                    ideal_selection[
                        adaptation_set.id
                    ] = self.choose_ideal_selection_bandwidth_based(
                        adaptation_set, bw_per_audio
                    )
        # print("\nIdeal Selection: ", ideal_selection)
        ideal_selection = {0: 3}
        print("\nIdeal Selection: ", ideal_selection)
        return ideal_selection

    @staticmethod
    def choose_ideal_selection_bandwidth_based(adaptation_set, bw) -> int:
        """
        Choose the ideal bitrate selection for one adaptation_set without caring about the buffer level or any other things

        Parameters
        ----------
        adaptation_set
            The adaptation_set to choose
        bw
            The bandwidth could be allocated to this adaptation set
        Returns
        -------
        id: int
            The representation id
        """
        representations = sorted(
            adaptation_set.representations.values(),
            key=lambda x: x.bandwidth,
            reverse=True,
        )
        representation = None
        for representation in representations:
            if representation.bandwidth < bw:
                return representation.id
        # If there's no representation whose bitrate is lower than the estimate, return the lowest one
        return representation.id

    def buffer_based(self, adaptation_sets: Dict[int, AdaptationSet]) -> Dict[int, int]:
        # print("\nSelected buffer-based ABR algorithm \n")
        final_selections = dict()

        for adaptation_set in adaptation_sets.values():
            final_selections[
                adaptation_set.id
            ] = self.choose_ideal_selection_buffer_based(adaptation_set)
        print("\nFinal Selections: ", final_selections)
        # print(final_selections)
        return final_selections

    def get_rate_map(self, bitrates):
        """
        Module to generate the rate map for the bitrates, reservoir, and cushion
        """
        rate_map = OrderedDict()
        rate_map[self.RESERVOIR] = bitrates[0]
        intermediate_levels = bitrates[1:-1]
        marker_length = (self.UPPER_RESERVOIR - self.RESERVOIR) / (
            len(intermediate_levels) + 1
        )
        current_marker = self.RESERVOIR + marker_length
        for bitrate in intermediate_levels:
            rate_map[current_marker] = bitrate
            current_marker += marker_length
        rate_map[self.UPPER_RESERVOIR] = bitrates[-1]
        return rate_map

    def choose_ideal_selection_buffer_based(self, adaptation_set) -> int:
        """
        Module that estimates the next bitrate based on the rate map.
        Rate Map: Buffer Occupancy vs. Bitrates:
            If Buffer Occupancy < RESERVOIR (10%) :
                select the minimum bitrate
            if RESERVOIR < Buffer Occupancy < Cushion(90%) :
                Linear function based on the rate map
            if Buffer Occupancy > Cushion :
                Maximum Bitrate
        Ref. Fig. 6 from [1]

        :param current_buffer_occupancy: Current buffer occupancy in number of segments
        :param bitrates: List of available bitrates [r_min, .... r_max]
        :return:the bitrate for the next segment
        """
        next_bitrate = None

        bitrates = [
            representation.bandwidth
            for representation in adaptation_set.representations.values()
        ]
        bitrates.sort()  # -> [391570, 641379, 988603, 1489543, 2284798, 3487003, 5253818]
        # Calculate the current buffer occupancy percentage
        current_buffer_occupancy = self.buffer_manager.buffer_level
        print("\nCurrent buffer occupancy: ", current_buffer_occupancy)
        print("\n")

        buffer_percentage = current_buffer_occupancy / self.buffer_size
        print("\nbuffer_precentage", buffer_percentage)

        # Selecting the next bitrate based on the rate map
        if self.rate_map == None:
            self.rate_map = self.get_rate_map(bitrates)

        if buffer_percentage <= self.RESERVOIR:
            next_bitrate = bitrates[0]
        elif buffer_percentage >= self.UPPER_RESERVOIR:
            next_bitrate = bitrates[-1]
        else:
            for marker in reversed(self.rate_map.keys()):
                if marker < buffer_percentage:
                    break
                next_bitrate = self.rate_map[marker]

        representation_id = None
        for representation in adaptation_set.representations.values():
            if representation.bandwidth == next_bitrate:
                representation_id = representation.id
        print("\nRepresentation ID: ", representation_id)
        return representation_id

    def _find_representation_id_of_lowest_bitrate(
        self, adaptation_set: AdaptationSet
    ) -> int:
        """
        Find the representation ID with the lowest bitrate in a given adaptation set
        Parameters
        ----------
        adaptation_set:
            The adaptation set to process

        Returns
        -------
            The representation ID with the lowest bitrate
        """
        if adaptation_set.id in self._min_bitrate_representations:
            return self._min_bitrate_representations[adaptation_set.id]

        min_id = None
        min_bandwidth = None

        for representation in adaptation_set.representations.values():
            if min_bandwidth is None:
                min_bandwidth = representation.bandwidth
                min_id = representation.id
            elif representation.bandwidth < min_bandwidth:
                min_bandwidth = representation.bandwidth
                min_id = representation.id
        self._min_bitrate_representations[adaptation_set.id] = min_id

        return min_id
