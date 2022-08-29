#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#
from typing import Any, Iterable, Mapping, MutableMapping, Optional

import pendulum
import requests
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams.http import HttpSubStream

from source_braze.streams import BrazeStream


class CanvasList(BrazeStream):
    use_cache = True
    primary_key = "canvas_id"
    _current_page = 0

    def path(
            self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "canvas/list"

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        if response.status_code == 200:
            # if the response is a success and items are 100, we need to get the next page
            # otherwise, we're done
            if 'canvases' in response.json() and len(response.json()['canvases']) == 100:
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
        canvases = response.json()["canvases"]
        for canvas in canvases:
            canvas[self.primary_key] = canvas["id"]
            yield canvas

    def request_params(
            self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, any] = None, next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        self.logger.info(
            f'Fetching {self.name} page: {self._current_page} of {self._pages}')
        return {
            "page": next_page_token["page"] if next_page_token else self._current_page,
        }


class CanvasDetails(HttpSubStream, BrazeStream):
    primary_key = "canvas_id"

    def __init__(self, **kwargs):
        super().__init__(CanvasList(**kwargs), **kwargs)

    def path(
            self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "canvas/details"

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

        # adding the canvas id to the canvas details object
        data[self.primary_key] = stream_slice["parent"][self.parent.primary_key]

        for step in data["steps"]:
            # adding the extra key "step_id"
            step["step_id"] = step["id"]

            # convert the messages object of a step to a list
            messages = []
            for message_id, message in step["messages"].items():
                message["message_id"] = message_id
                messages.append(message)
            step["messages"] = messages

        for variant in data["variants"]:
            variant["variant_id"] = variant["id"]

        yield data

    def request_params(
            self, stream_state: Mapping[str, Any], stream_slice: Mapping[str, any] = None, next_page_token: Mapping[str, Any] = None
    ) -> MutableMapping[str, Any]:
        self.logger.info(
            f'Fetching {self.name} canvas_id: {stream_slice["parent"][self.parent.primary_key]}')
        return {
            "canvas_id": stream_slice["parent"][self.parent.primary_key],
        }


class CanvasDataSeries(HttpSubStream, BrazeStream):
    primary_key = "canvas_id"
    date_template = "%Y-%m-%d"
    time_interval = {"days": 14}

    def __init__(self, **kwargs):
        super().__init__(CanvasDetails(**kwargs), **kwargs)
        self._start_date = pendulum.parse(kwargs["config"]["start_date"])

    def path(
            self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "canvas/data_series"

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

        # iterate through the stats
        for stat in data["stats"]:
            # adding the campaign id to the canvas data series object
            stat["canvas_id"] = stream_slice["parent"][self.parent.primary_key]

            # convert the variant_stats object of a step to a list
            variant_stats = []
            for variant_stat_id, variant_stat in stat.get("variant_stats", {}).items():
                variant_stat["variant_stat_id"] = variant_stat_id
                variant_stats.append(variant_stat)
            stat["variant_stats"] = variant_stats

            # convert the step_stats object of a step to a list
            step_stats = []
            for step_stat_id, step_stat in stat.get("step_stats", {}).items():
                step_stat["step_id"] = step_stat_id
                step_stats.append(step_stat)

                # convert the messages object of a step stat to a list
                new_messages = []
                for message_key, messages in step_stat.get("messages", {}).items():
                    for message in messages:
                        message["type"] = message_key
                        new_messages.append(message)
                step_stat["messages"] = new_messages

            stat["step_stats"] = step_stats

            yield stat

    def stream_slices(self, stream_state: Mapping[str, Any] = None, **kwargs) -> Iterable[Optional[Mapping[str, Any]]]:
        for parent_slice in super().stream_slices(sync_mode=SyncMode.full_refresh):
            if parent_slice["parent"]["first_entry"] is not None \
                    and parent_slice["parent"]["last_entry"] is not None:
                start_date = pendulum.parse(parent_slice["parent"]["first_entry"])
                end_date = pendulum.parse(parent_slice["parent"]["last_entry"])

                # if the campaign has as start date 1970, ignore it and continue
                if start_date == pendulum.parse("1970-01-01"):
                    continue

                if start_date.strftime(self.date_template) == end_date.strftime(self.date_template):
                    end_date = end_date.add(days=1)
            else:
                continue

            while start_date <= end_date:
                starting_at = start_date
                ending_at = start_date.add(**self.time_interval)

                # if ending day is after NOW(), set ending_at to NOW()
                if ending_at >= pendulum.now():
                    ending_at = pendulum.now()

                self.logger.info(
                    f"Fetching {self.name} canvas_id: {parent_slice['parent'][self.parent.primary_key]} ; time range: {starting_at.strftime(self.date_template)} - {ending_at.strftime(self.date_template)}")

                yield {
                    "parent": parent_slice["parent"],
                    "starting_at": starting_at.strftime(self.date_template),
                    "ending_at": ending_at.strftime(self.date_template),
                }
                start_date = start_date.add(**self.time_interval)

    def request_params(self, stream_slice: Mapping[str, Any], **kwargs) -> MutableMapping[str, Any]:
        return {
            "canvas_id": stream_slice["parent"][self.parent.primary_key],
            "starting_at": pendulum.parse(stream_slice["starting_at"]).strftime(self.date_template),
            "ending_at": pendulum.parse(stream_slice["ending_at"]).strftime(self.date_template),
            "include_variant_breakdown": "true",
            "include_step_breakdown": "true",
        }
