#
# Copyright (c) 2024 Airbyte, Inc., all rights reserved.
#
import csv
import gzip
import json
import re
from abc import ABC
from io import StringIO
from typing import Any, Iterable, Mapping, Optional, MutableMapping

import pendulum
import requests
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams.http import HttpStream, HttpSubStream
from airbyte_cdk.sources.streams.http.auth import NoAuth


class ASCStream(HttpStream, ABC):
    url_base = "https://api.appstoreconnect.apple.com"

    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)
        self._start_date = config["start_date"]
        self._end_date = config.get("end_date")

    def next_page_token(
        self, response: requests.Response
    ) -> Optional[Mapping[str, Any]]:
        if response.json().get("links", {}).get("next"):
            return {
                "next": response.json()["links"]["next"],
                "cursor": response.json()["links"]["next"].split("cursor=")[1],
            }
        return None

    def parse_response(
        self, response: requests.Response, **kwargs
    ) -> Iterable[Mapping]:
        yield from response.json()["data"]

    def get_json_schema(self):
        schema = super().get_json_schema()
        return schema


class AnalyticsReportRequests(ASCStream):
    primary_key = "id"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app_id = kwargs["config"]["app_id"]
        self.type_analytics_reports = kwargs["config"]["type_analytics_reports"]

    def path(
        self,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> str:
        if next_page_token:
            return next_page_token["next"]
        return f"/v1/apps/{self.app_id}/analyticsReportRequests"


class AnalyticsReports(HttpSubStream, ASCStream):
    primary_key = "id"

    def __init__(self, **kwargs):
        super().__init__(AnalyticsReportRequests(**kwargs), **kwargs)
        self.type_analytics_reports = kwargs["config"]["type_analytics_reports"]

    def next_page_token(
        self, response: requests.Response
    ) -> Optional[Mapping[str, Any]]:
        if response.json().get("links", {}).get("next"):
            return {
                "next": response.json()["links"]["next"],
                "cursor": response.json()["links"]["next"].split("cursor=")[1],
            }
        return None

    def path(
        self,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> str:
        if next_page_token:
            return next_page_token["next"]
        return f"/v1/analyticsReportRequests/{stream_slice['parent']['id']}/reports"

    def request_params(
        self,
        stream_state: Optional[Mapping[str, Any]],
        stream_slice: Optional[Mapping[str, Any]] = None,
        next_page_token: Optional[Mapping[str, Any]] = None,
    ) -> MutableMapping[str, Any]:
        return {
            "filter[category]": ",".join(self.type_analytics_reports),
        }


class AnalyticsReportInstances(HttpSubStream, ASCStream):
    primary_key = "id"
    time_interval = {"days": 1}
    window_attribution = {"days": 5}
    cursor_field = "processing_date"

    def __init__(self, **kwargs):
        super().__init__(AnalyticsReports(**kwargs), **kwargs)

    def path(
        self,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> str:
        if next_page_token:
            return next_page_token["next"]
        return f"/v1/analyticsReports/{stream_slice['parent']['id']}/instances"

    def request_params(
        self,
        stream_state: Optional[Mapping[str, Any]],
        stream_slice: Optional[Mapping[str, Any]] = None,
        next_page_token: Optional[Mapping[str, Any]] = None,
    ) -> MutableMapping[str, Any]:
        return {
            "filter[processingDate]": stream_slice["processing_date"],
            "filter[granularity]": "DAILY",
        }

    def stream_slices(
        self, sync_mode: SyncMode, stream_state: Mapping[str, Any] = None, **kwargs
    ) -> Iterable[Optional[Mapping[str, Any]]]:
        for parent_slice in super().stream_slices(sync_mode=sync_mode):
            stream_state = stream_state or {}
            if stream_state.get(self.cursor_field):
                start_date = pendulum.parse(stream_state[self.cursor_field])
                if (
                    pendulum.now().subtract(**self.window_attribution)
                    < start_date
                    < pendulum.now()
                ):
                    start_date = pendulum.parse(
                        stream_state[self.cursor_field]
                    ).subtract(**self.window_attribution)
            else:
                start_date = pendulum.parse(self._start_date)

            end_date = pendulum.parse(self._end_date or pendulum.now().to_date_string())

            while start_date <= end_date and start_date <= pendulum.parse(
                pendulum.now().to_date_string()
            ):
                yield {
                    **parent_slice,
                    "processing_date": start_date.to_date_string(),
                }
                start_date = start_date.add(days=1)


class AnalyticsReportSegments(HttpSubStream, ASCStream):
    primary_key = "id"

    def __init__(self, **kwargs):
        super().__init__(AnalyticsReportInstances(**kwargs), **kwargs)

    def path(
        self,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> str:
        if next_page_token:
            return next_page_token["next"]
        return f"/v1/analyticsReportInstances/{stream_slice['parent']['id']}/segments"


class AnalyticsReportData(HttpSubStream, ASCStream):
    primary_key = None

    def __init__(self, **kwargs):
        subkwargs = kwargs.copy()
        subkwargs["authenticator"] = NoAuth()
        super().__init__(
            AnalyticsReportSegments(**kwargs),
            **subkwargs,
        )

    def parse_response(
        self, response: requests.Response, **kwargs
    ) -> Iterable[Mapping]:
        def to_snake_case(name):
            # Convert to lower case and replace spaces with underscores
            name = re.sub(r"\s+", "_", name.strip().lower())
            # Replace CamelCase with snake_case
            name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
            return name

        # Decompress gzip data
        decompressed_data = gzip.decompress(response.content)

        # Convert bytes to string
        csv_data = decompressed_data.decode("utf-8")

        # Use StringIO to simulate a file-like object for csv.DictReader
        csv_file = StringIO(csv_data)

        # Read the CSV headers first and convert them to snake_case
        headers = csv_file.readline().strip().split(",")
        snake_case_headers = [to_snake_case(header) for header in headers]

        # Read CSV data
        csv_reader = csv.DictReader(csv_file, fieldnames=snake_case_headers)

        # Convert CSV to list of dictionaries
        data_list = [row for row in csv_reader]

        return data_list

    def path(
        self,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> str:
        return f"{stream_slice['parent']['attributes']['url']}"
