Low-level device driver architecture
====================================

The most essential function of `cct` is to communicate with hardware. This should however be done in a way that is

- efficient, i.e. allowing the highest throughput
- gives up-to-date information, responds to state changes "instantaneously" (or at least in very short time)
- reliable, i.e. fault tolerant
- keeps the main process / the user interface responsive

The backend process
-------------------

Most devices are "passive", i.e. do not send messages to the computer by themselves, only reply when queried. The large
number of devices and their state variables means that a single thread cannot handle both the communication and keep the
user interface responsive.

Each device (X-ray source, detector, motor controller, vacuum gauge, thermostat etc.) therefore has its own dedicated
subprocess, using the `multiprocessing` module of Python (to avoid problems with the GIL). This subprocess is
responsible for querying the device periodically and notify the main process only when the state of the device changes
(e.g. a position of a moving motor). All communication with the device is handled by this subprocess. Whenever the main
process wants the device to do something (e.g. move a motor, start an exposure with the detector or open the beam
shutter of the X-ray source), it contacts the subprocess and invokes one of its "commands". The subprocess and the
associated Python class is called the "backend".

The frontend process
--------------------

Each device has a "frontend" class as well, residing in the main process. It stores the most recent values of the state
variables and maintains contact with the backend through a pair of message queues. Whenever the backend sees a change
in a state variable, it notifies the frontend and sends the new value. The frontend then stores the new value.

The frontend blends well into the PyQt-based event loop. It periodically (through a timer event) checks the queue from
the backend and emits various signals (e.g. `variableChanged`). It also exposes the commands supported by the device
(e.g. to start an exposure or to set the value of a state variable) as member functions.

Implementation details of the backend
-------------------------------------

The backend process is a single process, implemented with coroutines using the `asyncio` module. At its core, there are
five tasks running as coroutines:

- processFrontendMessages:
    periodically check the queue for messages coming from the front-end and dispatch them.
- hardwareSender:
    send a message to the hardware whenever the hardware is ready to accept one
- hardwareReceiver:
    receive a message from the hardware and ensure that it is interpreted
- autoquerier:
    periodically schedule queries to the hardware on changes of state variables
- telemetry:
    periodically send debugging statistics to the frontend

Messages sent by the backend object
-----------------------------------

variablenames:
    the first message sent by the backend, its data is a list of names and timeouts of each variable
end:
    the last message sent by the backend, its data is a single boolean flag: if True, the termination of the backend is expected (i.e. upon request by the frontend), if False, it is unexpected (e.g. hardware/connection error)
log:
    a log message to be sent to the frontend. The frontend then inserts this into the dedicated `backend logging stream`.
telemetry:
    some operational data and statistics sent to the frontend. These are mostly for debugging purposes.
commandfinished:
    a command requested by the frontend has finished successfully. The command name and its optional result is sent back to the frontend.
commanderror:
    a command requested by the frontend was unsuccessful. The command name and the error message is sent back to the frontend.
variableChanged:
    a state variable has changed. The variable name, the new and the previous value is sent back.
ready:
    sent when the value of all variables has been read at least once. When this message is sent to the frontend, the device is considered fully initialized and operational.

Lifetime of a device object
---------------------------

  1. The device frontend object is always initialized from the main thread, by the DeviceManager component of the Instrument class.
  2. The backend process is automatically initialized by the frontend
  3. The backend sends a message of type `variablenames` to the frontend with a list of the defined variables
  4. The backend tries to initialize connection to the hardware. If not successful, it sends an `error` message to the frontend, and subsequently an `end` message with the `unexpected` flag set, and the backend process terminates.
  5. If the device is successfully connected to, the backend starts periodically sending messages to the device to query the status variables.
  6. Whenever the device replies back, the message is analyzed and the corresponding status variables are updated. If the value is different than the previous one on file, the frontend is notified by a `variableChanged` message.
  7. When all variables have been initialized (read at least one), the `ready` message is sent to the frontend. Only after this point is the backend considered fully operational.
  8.




