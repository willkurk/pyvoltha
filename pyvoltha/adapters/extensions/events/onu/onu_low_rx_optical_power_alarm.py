# Copyright 2018 the original author or authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from voltha_protos.events_pb2 import AlarmEventType, AlarmEventSeverity, AlarmEventCategory
from pyvoltha.adapters.extensions.alarms.adapter_alarms import AlarmBase


class OnuLowRxOpticalAlarm(AlarmBase):
    """
    The ONU Low Rx Optical Power Alarm is reported by the ANI-G (ME # 263) to
    indicate that the received downstream optical power below threshold.

    For ANI-G equipment alarms, the intf_id reported is that of the PON/ANI
    physical port number
    """
    def __init__(self, alarm_mgr, onu_id, intf_id, serial_number):
        super(OnuLowRxOpticalAlarm, self).__init__(alarm_mgr, object_type='onu low rx optical power',
                                                   alarm='ONU_LOW_RX_OPTICAL',
                                                   alarm_category=AlarmEventCategory.ONU,
                                                   alarm_type=AlarmEventType.COMMUNICATION,
                                                   alarm_severity=AlarmEventSeverity.MAJOR)
        self._onu_id = onu_id
        self._intf_id = intf_id
        self._serial_number = serial_number

    def get_context_data(self):
        return {'onu-id': self._onu_id,
                'onu-intf-id': self._intf_id,
                'onu-serial-number': self._serial_number}
