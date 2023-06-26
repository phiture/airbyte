#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional

import pendulum
import requests
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams import IncrementalMixin
from airbyte_cdk.sources.streams.http import HttpSubStream
from source_phiture_braze.streams import BrazeStream


class SegmentsList(BrazeStream):
    use_cache = True
    primary_key = "segment_id"
    _current_page = 0

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "segments/list"

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        if response.status_code == 200:
            # if the response is a success and items are 100, we need to get the next page
            # otherwise, we're done
            if "segments" in response.json() and len(response.json()["segments"]) == 100:
                if self._current_page < self._pages:
                    self._current_page += 1
                    return {"page": self._current_page}
            else:
                return None

        return None

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        # The response is a simple JSON whose schema matches our stream's schema exactly,
        # so we just return a list containing the response
        segments = response.json()["segments"]
        for segment in segments:
            segment[self.primary_key] = segment["id"]
            yield segment

    def request_params(
        self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, any] = None, next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        self.logger.info(f"Fetching {self.name} page: {self._current_page} of {self._pages}")
        return {
            "page": next_page_token["page"] if next_page_token else self._current_page,
        }


class SegmentsDetails(HttpSubStream, BrazeStream):
    primary_key = "segment_id"

    def __init__(self, **kwargs):
        super().__init__(SegmentsList(**kwargs), **kwargs)

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "segments/details"

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        # The response is a simple JSON whose schema matches our stream's schema exactly,
        # so we just return a list containing the response
        data = response.json()

        # adding the segment id to the segment details object
        data[self.primary_key] = stream_slice["parent"][self.parent.primary_key]

        yield data

    def request_params(
        self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, any] = None, next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        self.logger.info(f'Fetching {self.name} segment_id: {stream_slice["parent"][self.parent.primary_key]}')
        return {
            "segment_id": stream_slice["parent"][self.parent.primary_key],
        }


class SegmentsDataSeries(HttpSubStream, BrazeStream):
    time_interval = {"days": 100}
    primary_key = ["segment_id", "time"]

    def __init__(self, **kwargs):
        super().__init__(SegmentsDetails(**kwargs), **kwargs)

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "segments/data_series"

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        # The response is a simple JSON whose schema matches our stream's schema exactly,
        # so we just return a list containing the response
        data = response.json()["data"]

        # iterate through the data
        for serie in data:
            # adding the segment id to the segment data series object
            serie[self.parent.primary_key] = stream_slice["parent"][self.parent.primary_key]

            yield serie

    def stream_slices(self, sync_mode: SyncMode, stream_state: Mapping[str, Any] = None, **kwargs) -> Iterable[Optional[Mapping[str, Any]]]:
        for parent_slice in super().stream_slices(sync_mode=sync_mode):
            if parent_slice["parent"]["created_at"] is None or parent_slice["parent"]["updated_at"] is None:
                continue

            start_date = pendulum.parse(parent_slice["parent"]["created_at"])
            end_date = pendulum.parse(parent_slice["parent"]["updated_at"])

            if start_date.to_date_string() == end_date.to_date_string():
                end_date = end_date.add(days=1)

            while start_date <= end_date:
                starting_at = start_date.start_of("day")
                ending_at = min(starting_at.add(days=self.time_interval["days"]).end_of("day"), end_date.end_of("day"))

                # if ending day is after NOW(), set ending_at to NOW()
                if ending_at >= pendulum.now().utcnow():
                    ending_at = pendulum.now().utcnow()

                self.logger.info(
                    f"Fetching {self.name} segment_id: {parent_slice['parent'][self.parent.primary_key]} ; time range: {starting_at.to_iso8601_string()} - {ending_at.to_iso8601_string()}"
                )

                yield {
                    "parent": parent_slice["parent"],
                    "starting_at": starting_at.to_iso8601_string(),
                    "ending_at": ending_at.to_iso8601_string(),
                }
                start_date = start_date.add(days=self.time_interval["days"])

    def request_params(self, stream_slice: Mapping[str, Any], **kwargs) -> MutableMapping[str, Any]:
        return {
            "segment_id": stream_slice["parent"][self.parent.primary_key],
            "length": self.time_interval["days"],
            "ending_at": stream_slice["ending_at"],
        }
