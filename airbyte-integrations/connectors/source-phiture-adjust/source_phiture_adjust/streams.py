#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#
from abc import ABC
from typing import Any, Iterable, List, Mapping, MutableMapping, Optional

import pendulum
import requests
from airbyte_cdk.models import SyncMode
from airbyte_cdk.sources.streams.http import HttpStream
from source_phiture_adjust.util_report_service import (
    ad_spend_metrics_list,
    conversion_metrics_list,
    dimensions,
    event_metrics_list,
    revenue_metrics_list,
    skad_metrics_list,
)


class ReportService(HttpStream, ABC):
    url_base = "https://dash.adjust.com"

    primary_key = None
    cursor_field = "day"
    time_interval = {"days": 1}
    state_checkpoint_interval = 1000
    _metrics = None
    # the window attribution is used to re-fetch the last 30 days of data
    #  only if the last state day is in the range of the last 30 days
    window_attribution = {"days": 30}

    def __init__(self, config: Mapping[str, Any], dimensions: List[str], metrics: List[str], **kwargs):
        super().__init__(**kwargs)
        self._state = {}

        self._app_token = config["app_token"]
        self._start_date = config["start_date"]
        self._end_date = config.get("end_date")
        self._attribution_type = config.get("attribution_type")
        self._ad_spend_mode = config.get("ad_spend_mode")
        self._currency = config.get("currency")
        self._dimensions = dimensions
        self._metrics = metrics

        self.primary_key = dimensions

    @property
    def state(self) -> MutableMapping[str, Any]:
        return self._state

    @state.setter
    def state(self, value: MutableMapping[str, Any]):
        self._state.update(value)

    def next_page_token(self, response: requests.Response) -> Optional[Mapping[str, Any]]:
        """
        TODO: Override this method to define a pagination strategy. If you will not be using pagination, no action is required - just return None.
        This method should return a Mapping (e.g: dict) containing whatever information required to make paginated requests. This dict is passed
        to most other methods in this class to help you form headers, request bodies, query params, etc..
        For example, if the API accepts a 'page' parameter to determine which page of the result to return, and a response from the API contains a
        'page' number, then this method should probably return a dict {'page': response.json()['page'] + 1} to increment the page count by 1.
        The request_params method should then read the input next_page_token and set the 'page' param to next_page_token['page'].
        :param response: the most recent response from the API
        :return If there is another page in the result, a mapping (e.g: dict) containing information needed to query the next page in the response.
                If there are no more pages in the result, return None.
        """
        return None

    def current_state(self, canvas_id, default=None):
        default = default or self.state.get(self.cursor_field)
        return self.state.get(canvas_id, {}).get(self.cursor_field) or default

    def path(
        self, stream_state: Mapping[str, Any] = None, stream_slice: Mapping[str, Any] = None, next_page_token: Mapping[str, Any] = None
    ) -> str:
        return "control-center/reports-service/report"

    def request_params(
        self,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> MutableMapping[str, Any]:
        return {
            "app_token__in": self._app_token,
            "date_period": f'{stream_slice["start_date"]}:{stream_slice["end_date"]}',
            "dimensions": ",".join(self._dimensions),
            "metrics": ",".join(self._metrics),
            "attribution_type": self._attribution_type,
            "ad_spend_mode": self._ad_spend_mode,
            "currency": self._currency,
        }

    def parse_response(
        self,
        response: requests.Response,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> Iterable[Mapping]:
        data = response.json()
        for row in data["rows"]:
            yield row

    def stream_slices(self, sync_mode: SyncMode, stream_state: Mapping[str, Any] = None, **kwargs) -> Iterable[Optional[Mapping[str, Any]]]:
        stream_state = stream_state or {}

        if stream_state.get("last_sync"):
            start_date = pendulum.parse(stream_state["last_sync"].get(self.cursor_field))
            if pendulum.now().subtract(**self.window_attribution) < start_date < pendulum.now():
                start_date = pendulum.parse(stream_state["last_sync"].get(self.cursor_field)).subtract(**self.window_attribution)
        else:
            start_date = pendulum.parse(self._start_date)

        end_date = pendulum.parse(self._end_date or pendulum.now().to_date_string())

        while start_date <= end_date and start_date < pendulum.parse(pendulum.now().to_date_string()):
            starting_at = start_date
            ending_at = start_date

            self.logger.info(f"Fetching {self.name} ; time range: {starting_at.to_date_string()} - {ending_at.to_date_string()}")

            yield {
                "start_date": starting_at.to_date_string(),
                "end_date": ending_at.to_date_string(),
            }
            start_date = start_date.add(**self.time_interval)

    def read_records(
        self, sync_mode: SyncMode, cursor_field: List[str] = None, stream_slice: MutableMapping[str, Any] = None, **kwargs
    ) -> Iterable[Mapping[str, Any]]:
        for record in super().read_records(sync_mode=sync_mode, stream_slice=stream_slice):
            current_state = self.current_state(self._app_token)
            if current_state:
                date_in_current_stream = pendulum.parse(current_state)
                date_in_latest_record = pendulum.parse(record[self.cursor_field])
                cursor_value = (max(date_in_current_stream, date_in_latest_record)).to_date_string()
                self.state = {self._app_token: {self.cursor_field: cursor_value}}
                yield record
                continue
            self.state = {self._app_token: {self.cursor_field: record[self.cursor_field]}}
            yield record


class ReportServiceConversionMetrics(ReportService):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(config, dimensions=dimensions, metrics=conversion_metrics_list, **kwargs)


class ReportServiceAdSpendMetrics(ReportService):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(config, dimensions=dimensions, metrics=ad_spend_metrics_list, **kwargs)


class ReportServiceRevenueMetrics(ReportService):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(config, dimensions=dimensions, metrics=revenue_metrics_list, **kwargs)


class ReportServiceSkadMetrics(ReportService):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(config, dimensions=dimensions, metrics=skad_metrics_list, **kwargs)


class ReportServiceEventMetrics(ReportService):
    def __init__(self, config: Mapping[str, Any], **kwargs):
        super().__init__(config, dimensions=dimensions, metrics=event_metrics_list, **kwargs)
