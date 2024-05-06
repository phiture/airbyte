#
# Copyright (c) 2024 Airbyte, Inc., all rights reserved.
#


import datetime
from typing import Any, List, Mapping, Tuple

import jwt
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http.requests_native_auth.abstract_token import (
    AbstractHeaderAuthenticator,
)

from .streams import (
    AnalyticsReportRequests,
    AnalyticsReports,
    AnalyticsReportInstances,
    AnalyticsReportSegments,
    AnalyticsReportData,
)


class MyCustomTokenAuthenticator(AbstractHeaderAuthenticator):
    def __init__(
        self,
        issuer_id: str,
        key_id: str,
        key_contents: str,
    ):
        self._auth_method = "Bearer"
        self._auth_header = "Authorization"
        self._issuer_id = issuer_id
        self._key_id = key_id
        self._key_contents = key_contents

    @property
    def auth_header(self):
        return self._auth_header

    @property
    def token(self):
        return f"{self._auth_method} {self.generate_token()}"

    def generate_token(self) -> str:
        """
        Generate a JWT token string.
        :return: A JWT token string.
        """
        expiration_minutes = 20
        expiration_time = datetime.datetime.utcnow() + datetime.timedelta(
            minutes=expiration_minutes
        )

        # Define the token header
        header = {"alg": "ES256", "kid": self._key_id, "typ": "JWT"}

        # Define the token payload
        payload = {
            "iss": self._issuer_id,
            "iat": datetime.datetime.utcnow(),
            "exp": expiration_time,
            "aud": "appstoreconnect-v1",
        }

        # Generate the token
        token = jwt.encode(
            payload, self._key_contents, algorithm="ES256", headers=header
        )

        return token


class SourcePhitureAppStoreConnect(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        # check that start_date and end_date are valid dates (end_date is optional) and that end_date is after start_date
        start_date = config["start_date"]
        end_date = config.get("end_date")

        try:
            datetime.datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            return (
                False,
                "start_date is not in the correct format. Should be YYYY-MM-DD",
            )

        if end_date:
            try:
                datetime.datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                return (
                    False,
                    "end_date is not in the correct format. Should be YYYY-MM-DD",
                )

            if start_date > end_date:
                return False, "end_date should be after start_date"

        return True, None

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        auth = MyCustomTokenAuthenticator(
            issuer_id=config["issuer_id"],
            key_id=config["key_id"],
            key_contents=config["key_contents"],
        )
        return [
            AnalyticsReportRequests(
                authenticator=auth,
                config=config,
            ),
            AnalyticsReports(
                authenticator=auth,
                config=config,
            ),
            AnalyticsReportInstances(
                authenticator=auth,
                config=config,
            ),
            AnalyticsReportSegments(
                authenticator=auth,
                config=config,
            ),
            AnalyticsReportData(
                authenticator=auth,
                config=config,
            ),
        ]
