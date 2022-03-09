import logging
import colorlog

logging.STRONGINFO = logging.DEBUG + 5
logging.addLevelName(logging.STRONGINFO, 'STRONGINFO')


def logStrongInfo(msg, *args, **kwargs):
    """Log a message with severity 'STRONGINFO' on the root logger. If the logger has
    no handlers, call basicConfig() to add a console handler with a pre-defined
    format."""
    return logging.log(logging.STRONGINFO, msg, *args, **kwargs)


setattr(logging, 'stronginfo', logStrongInfo)


def logStrongInfoMethod(self, msg, *args, **kwargs):
    """Log 'msg % args' with severity 'STRONGINFO'.

    To pass exception information, use the keyword argument exc_info with
    a true value, e.g.

    logger.stronginfo("Houston, we have a %s", "interesting problem", exc_info=1)
    """
    return self.log(logging.STRONGINFO, msg, *args, **kwargs)


setattr(logging.getLoggerClass(), 'stronginfo', logStrongInfoMethod)

colorlog.default_log_colors['STRONGINFO'] = 'bold_green'

