import email, email.utils, email.message
import logging
import re
import smtplib
import traceback
from typing import Sequence, Optional, List, Any, Tuple

import dbus
import pkg_resources
from PyQt5 import QtCore

from .component import Component

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class NotificationAddress:
    name: Optional[str] = None
    emailaddress: Optional[str] = None
    panic: bool = True
    runtime: bool = True
    loglevel: int = logging.ERROR

    def __init__(self, name: str = 'Anonymous', emailaddress: Optional[str] = None, panic: bool = False,
                 runtime: bool = False, loglevel: int = logging.ERROR):
        self.name = name
        self.emailaddress = emailaddress
        self.panic = panic
        self.loglevel = loglevel
        self.runtime = runtime


class Notifier(QtCore.QAbstractItemModel, Component, logging.Handler):
    _data: List[NotificationAddress]
    email_ratelimit_interval: float = 10.0  # seconds
    email_ratelimit_buffer: List[Tuple[email.message.EmailMessage, List[str]]]
    email_timer_handle: Optional[int] = None
    email_ratelimit_buffer_maxlength = 1000
    re_valid_email = re.compile(r'(?P<username>[-a-zA-Z_.0-9]+)@(?P<hostname>[-a-zA-Z0-9._]+)')

    def __init__(self, **kwargs):
        self.email_ratelimit_buffer = []
        self._data = []
        super().__init__(**kwargs)
        logging.Handler.__init__(self)
        self.setFormatter(logging.Formatter('%(asctime)s: %(levelname)s: %(name)s: %(message)s'))

    def saveToConfig(self):
        if 'notifier' not in self.config:
            self.config['notifier'] = {}
        self.config['notifier']['addresses'] = {}
        for i, address in enumerate(self._data):
            self.config['notifier']['addresses'][f'{i:08d}'] = {
                'name': address.name,
                'emailaddress': address.emailaddress,
                'panic': address.panic,
                'runtime': address.runtime,
                'loglevel': address.loglevel
            }
        self.config.save()

    def loadFromConfig(self):
        if 'notifier' not in self.config:
            self.config['notifier'] = {}
        self.beginResetModel()
        try:
            self._data = []
            if 'addresses' not in self.config['notifier']:
                self.config['notifier']['addresses'] = {}
            for key in sorted(self.config['notifier']['addresses']):
                self._data.append(NotificationAddress(
                    self.config['notifier']['addresses'][key]['name'],
                    self.config['notifier']['addresses'][key]['emailaddress'],
                    self.config['notifier']['addresses'][key]['panic'],
                    self.config['notifier']['addresses'][key]['runtime'],
                    self.config['notifier']['addresses'][key]['loglevel']
                ))
        finally:
            self.endResetModel()

    @property
    def smtpserver(self) -> Optional[str]:
        try:
            return self.config['notifier']['smtpserver']
        except KeyError:
            try:
                self.config['notifier']['smtpserver'] = None
            except KeyError:
                pass
            return None

    @smtpserver.setter
    def smtpserver(self, value: Optional[str]):
        self.config['notifier']['smtpserver'] = value
        self.saveToConfig()

    @property
    def fromaddress(self) -> Optional[str]:
        try:
            return self.config['notifier']['fromaddress']
        except KeyError:
            self.config['notifier']['fromaddress'] = None
            return None

    @fromaddress.setter
    def fromaddress(self, value: Optional[str]):
        self.config['notifier']['fromaddress'] = value
        self.saveToConfig()

    @staticmethod
    def notify_desktop(title: str, body: str, expiretimeout: int = 10000, iconfile: str = 'cct4logo.svg'):
        dbus.Interface(
            dbus.SessionBus().get_object(
                'org.freedesktop.Notifications', '/org/freedesktop/Notifications'),
            'org.freedesktop.Notifications').Notify(
            'cct',  # app_name
            0,  # replaces_id
            pkg_resources.resource_filename('cct', f'resource/icons/{iconfile}'),  # app_icon
            title,  # summary
            body,  # body
            [],  # actions
            {'sound-name': 'dialog-information'},  # hints
            expiretimeout  # expire_timeout
        )

    def notify_email(self, title: str, body: str, emailaddresses: Sequence[str]):
        emailaddresses = [a for a in emailaddresses if self.re_valid_email.match(a)]
        if not emailaddresses:
            print('Not sending e-mails, empty address list.')
            return
        if (self.smtpserver is None) or (self.fromaddress is None):
            logger.debug('Not sending e-mail: either smtpserver or fromaddress or toaddress is None.')
            return
        m = re.match(r'(?P<host>[^:]+)(?::(?P<port>\d+))?', self.smtpserver)
        if not m:
            print(f'Malformed smtp host: {self.smtpserver}')
            return
        msg = email.message.EmailMessage()
        msg.set_content(body)
        msg['Subject'] = title
        msg['From'] = email.utils.formataddr(('SAXS instrument control', self.fromaddress))
        msg['Message-ID'] = email.utils.make_msgid()
        msg['Date'] = email.utils.localtime()
        self.queue_email(msg, emailaddresses)

    def panichandler(self):
        try:
            self.notify_desktop(
                'Panic in the SAXS instrument',
                f'Panic situation occurred in the SAXS instrument: {self.instrument.panicreason}.')
            self.notify_email(
                f'[PANIC] Panic in the SAXS instrument',
                f'There was a panic incident in the SAXS instrument. The reason: {self.instrument.panicreason}.',
                set([n.emailaddress for n in self._data if (n.emailaddress is not None) and (n.panic)] + [
                    self.instrument.auth.currentUser().email])
            )
        except:
            print(traceback.format_exc())
        self._panicking = self.PanicState.Panicked
        QtCore.QTimer.singleShot(1, QtCore.Qt.VeryCoarseTimer, self.panicAcknowledged.emit)

    def queue_email(self, message: email.message.EmailMessage, addressee: List[str]):
        if len(self.email_ratelimit_buffer) >= self.email_ratelimit_buffer_maxlength:
            self.email_ratelimit_buffer = []
            self.instrument.panic('E-mail send buffer overflow, messages lost.')
        else:
            self.email_ratelimit_buffer.append((message, addressee))
        if self.email_timer_handle is None:
            self.email_timer_handle = self.startTimer(0, QtCore.Qt.PreciseTimer)

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        """Send an e-mail waiting in the queue
        :param event: the timer event
        :type event: QtCore.QTimerEvent
        """
        if not self.email_ratelimit_buffer:
            # if no e-mails are pending in the buffer (should not happen normally, but who knows)
            self.killTimer(self.email_timer_handle)
            self.email_timer_handle = None
            return
        # try to get the SMTP server
        m = re.match(r'(?P<host>[^:]+)(?::(?P<port>\d+))?', self.smtpserver)
        if not m:
            # Invalid SMTP host: empty the buffer, stop the timer
            print(f'Malformed smtp host: {self.smtpserver}')
            self.email_ratelimit_buffer = []
            self.killTimer(self.email_timer_handle)
            self.email_timer_handle = None
            return
        s = None
        try:
            # connect to the SMTP server
            s = smtplib.SMTP(m['host'], int(m['port']) if m['port'] is not None else None)
            # send a single message
            msg, emailaddresses = self.email_ratelimit_buffer.pop(0)
            for addressee in emailaddresses:
#                print(f'Sending e-mail to "{addressee}"')
                msg['To'] = addressee
                s.send_message(msg, self.fromaddress, addressee)
        except:
            # print the exception: any unhandled exceptions may result in an infinite loop
            traceback.print_exc()
        finally:
            if s is not None:
                s.quit()
        # we always kill the timer and reinitialize if needed.
        self.killTimer(self.email_timer_handle)
        self.email_timer_handle = None
        if self.email_ratelimit_buffer:
            self.email_timer_handle = self.startTimer(int(self.email_ratelimit_interval*1000), QtCore.Qt.PreciseTimer)

    def rowCount(self, parent: QtCore.QModelIndex = ...) -> int:
        if (not isinstance(parent, QtCore.QModelIndex)) or (not parent.isValid()):
            return len(self._data)
        else:
            return 0

    def columnCount(self, parent: QtCore.QModelIndex = ...) -> int:
        return 5

    def index(self, row: int, column: int, parent: QtCore.QModelIndex = ...) -> QtCore.QModelIndex:
        if (not isinstance(parent, QtCore.QModelIndex)) or (not parent.isValid()):
            return self.createIndex(row, column, None)
        else:
            return QtCore.QModelIndex()

    def parent(self, child: QtCore.QModelIndex) -> QtCore.QModelIndex:
        return QtCore.QModelIndex()

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemNeverHasChildren

    def data(self, index: QtCore.QModelIndex, role: int = ...) -> Any:
        if (index.column() == 0) and (role == QtCore.Qt.DisplayRole):
            return self._data[index.row()].name if self._data[index.row()].name is not None else '--'
        elif (index.column() == 1) and (role == QtCore.Qt.DisplayRole):
            return self._data[index.row()].emailaddress if self._data[index.row()].emailaddress is not None else '--'
        elif (index.column() == 2) and (role == QtCore.Qt.DisplayRole):
            return 'YES' if self._data[index.row()].panic else 'NO'
        elif (index.column() == 3) and (role == QtCore.Qt.DisplayRole):
            return 'YES' if self._data[index.row()].runtime else 'NO'
        elif (index.column() == 4) and (role == QtCore.Qt.DisplayRole):
            return f'{self._data[index.row()].loglevel:d} ({logging.getLevelName(self._data[index.row()].loglevel)})'
        elif (index.column() == 0) and (role == QtCore.Qt.EditRole):
            return self._data[index.row()].name
        elif (index.column() == 1) and (role == QtCore.Qt.EditRole):
            return self._data[index.row()].emailaddress
        elif (index.column() == 2) and (role == QtCore.Qt.EditRole):
            return self._data[index.row()].panic
        elif (index.column() == 3) and (role == QtCore.Qt.EditRole):
            return self._data[index.row()].runtime
        elif (index.column() == 4) and (role == QtCore.Qt.EditRole):
            return self._data[index.row()].loglevel
        else:
            return None

    def insertRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.insertRows(row, 1, parent)

    def insertRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            return False
        else:
            self.beginInsertRows(QtCore.QModelIndex(), row, row + count - 1)
            if row >= len(self._data):
                for i in range(count):
                    self._data.append(NotificationAddress())
            else:
                for i in range(count):
                    self._data.insert(row, NotificationAddress())
            self.saveToConfig()
            self.endInsertRows()

    def removeRows(self, row: int, count: int, parent: QtCore.QModelIndex = ...) -> bool:
        if isinstance(parent, QtCore.QModelIndex) and parent.isValid():
            return False
        else:
            self.beginRemoveRows(QtCore.QModelIndex(), row, row + count - 1)
            del self._data[row:row + count]
            self.endRemoveRows()
            self.saveToConfig()
            return True

    def removeRow(self, row: int, parent: QtCore.QModelIndex = ...) -> bool:
        return self.removeRows(row, 1, parent)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = ...) -> Any:
        if (orientation == QtCore.Qt.Horizontal) and (role == QtCore.Qt.DisplayRole):
            return \
            ['Name', 'E-mail address', 'Notify on panic?', 'Send runtime notifications?', 'Log level to notify on'][
                section]

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = ...) -> bool:
        if (index.column() == 0) and (role == QtCore.Qt.EditRole):
            self._data[index.row()].name = str(value)
        elif (index.column() == 1) and (role == QtCore.Qt.EditRole):
            self._data[index.row()].emailaddress = str(value)
        elif (index.column() == 2) and (role == QtCore.Qt.EditRole):
            self._data[index.row()].panic = bool(value)
        elif (index.column() == 3) and (role == QtCore.Qt.EditRole):
            self._data[index.row()].runtime = bool(value)
        elif (index.column() == 4) and (role == QtCore.Qt.EditRole):
            self._data[index.row()].loglevel = int(value)
        else:
            return False
        self.saveToConfig()
        return True

    def emit(self, record: logging.LogRecord):
        """Format the log message for an e-mail body and send an e-mail"""
        if not record.name.startswith('cct'):
            # this is a log message from somewhere else, e.g. matplotlib
            return
        try:
            if (self.smtpserver is None) or (self.fromaddress is None):
                return
            emailaddresses = [n.emailaddress for n in self._data if
                              (n.loglevel <= record.levelno) and (n.emailaddress is not None)]
            if not emailaddresses:
                # speed up
                return
            msg = f'Please be notified for the following log message from the SAXS instrument:\n'
            msg += f'Log level: {record.levelno:d} ({record.levelname})\n'
            msg += f'Time: {record.asctime}\n'
            msg += f'Message: {record.getMessage()}\n'
            msg += f'Logger name: {record.name}\n'
            msg += f'Occurred in file: {record.pathname}\n'
            msg += f'Line number: {record.lineno}\n'
            msg += f'Module: {record.module}\n'
            msg += f'Function name: {record.funcName}\n'
            msg += f'Stack info: {record.stack_info}\n'
            self.notify_email(f'[{record.levelname}] in {record.module}:{record.funcName}', msg, emailaddresses)
        except Exception as exc:
            # swallow the exception: unhandled exceptions return in a CRITICAL log event, resulting in an infinite loop.
            print(traceback.format_exc())

    def notify(self, title: str, body: str):
        """Send notification to desktop and the current user"""
        self.notify_desktop(title, body)
        emails = set([n.emailaddress for n in self._data if (n.runtime) and (n.emailaddress is not None)] + [
            self.instrument.auth.currentUser().email])
        self.notify_email(title, body, emailaddresses=list(emails))

    def startComponent(self):
        logger.debug('Starting component Notification')
        super().startComponent()
        logging.root.addHandler(self)
        self.setLevel(logging.INFO)
        logger.debug('Started component Notification')

    def stopComponent(self):
        logging.root.removeHandler(self)
        super().stopComponent()
