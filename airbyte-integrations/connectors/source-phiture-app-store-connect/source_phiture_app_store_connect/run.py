#
# Copyright (c) 2024 Airbyte, Inc., all rights reserved.
#


import sys

from airbyte_cdk.entrypoint import launch
from .source import SourcePhitureAppStoreConnect

def run():
    source = SourcePhitureAppStoreConnect()
    launch(source, sys.argv[1:])
