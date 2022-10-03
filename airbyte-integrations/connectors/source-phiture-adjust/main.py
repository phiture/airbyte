#
# Copyright (c) 2022 Airbyte, Inc., all rights reserved.
#


import sys

from airbyte_cdk.entrypoint import launch
from source_phiture_adjust import SourcePhitureAdjust

if __name__ == "__main__":
    source = SourcePhitureAdjust()
    launch(source, sys.argv[1:])
