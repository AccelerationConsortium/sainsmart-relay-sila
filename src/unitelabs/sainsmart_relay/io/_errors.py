"""
SiLA defined-execution errors for the SainSmart relay.

These are plain ``Exception`` subclasses (the current CDK convention). The CDK's
``define_error`` converts any exception listed in a command's ``errors=[...]`` into
a SiLA DefinedExecutionError, using the class name and docstring for the SiLA
identifier/description on the wire.
"""


class RelayCommunicationError(Exception):
    """The relay could not be reached or a serial command failed."""


class ChannelOutOfRange(Exception):
    """
    The requested channel is outside 0..num_channels-1.

    Defensive only: the SiLA ``Channel`` constraint already rejects out-of-range
    values at the protocol boundary.
    """
