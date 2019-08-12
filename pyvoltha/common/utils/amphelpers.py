from twisted.internet import reactor, task
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import reflect
from twisted.protocols import amp
from ampoule import pool, util
from ampoule import child
from pyvoltha.adapters.kafka.adapter_proxy import AdapterProxy
from pyvoltha.adapters.kafka.core_proxy import CoreProxy
from pyvoltha.adapters.extensions.omci.openomci_agent import OpenOMCIAgent, OpenOmciAgentDefaults
from pyvoltha.adapters.extensions.omci.omci_me import *
from pyvoltha.adapters.extensions.omci.database.mib_db_ext import MibDbExternal
from pyvoltha.common.utils.registry import registry, IComponent
from zope.interface import implementer
from pyvoltha.adapters.kafka.adapter_request_facade import InterAdapterRequestFacade
from pyvoltha.adapters.kafka.kafka_inter_container_library import IKafkaMessagingProxy, \
    get_messaging_proxy

from copy import deepcopy
import sys
sys.path.insert(0, "/voltha/")

from adapters.brcm_openomci_onu.brcm_openomci_onu_handler import BrcmOpenomciOnuHandler
from adapters.brcm_openomci_onu.omci.brcm_capabilities_task import BrcmCapabilitiesTask
from adapters.brcm_openomci_onu.omci.brcm_mib_sync import BrcmMibSynchronizer

import dill

from voltha_protos.device_pb2 import Device
from voltha_protos.inter_container_pb2 import InterContainerMessage

class OMCIAdapter:
    def __init__(self, process_parameters, broadcom_omci):
        self.process_parameters = process_parameters
        self.broadcom_omci = broadcom_omci

class BrcmAdapterShim:
    def __init__(self, core_proxy, adapter_proxy, omci_agent):
        self.core_proxy = core_proxy
        self.adapter_proxy = adapter_proxy
        self.omci_agent = omci_agent

@implementer(IComponent)
class MainShim:
    def __init__(self, args):
        self.args = args
    def get_args(self):
        return self.args

class ProcessMessage(amp.Argument):
        def toString(self, inObject):
            return inObject.SerializeToString()

        def fromString(self, inString):
            message = InterContainerMessage()
            message.ParseFromString(inString())
            return message

class OMCIDeviceParam(amp.Argument):
        def toString(self, inObject):
            #log.debug("serializing-device")
            return inObject.SerializeToString()

        def fromString(self, inString):
            device = Device()
            device.ParseFromString(inString)
            return device

class OMCIAdapterParam(amp.Argument):
        def toString(self, inObject):
            #log.debug("serializing-device")
            return dill.dumps(inObject)

        def fromString(self, inString):
            return dill.loads(inString)

class ProcessMessage(amp.Command):
    arguments = [('message', ProcessMessage())]
    response = [("success", amp.Integer())]

class Activate(amp.Command):
    arguments = [("device", OMCIDeviceParam()),
            ("adapter", OMCIAdapterParam())]
    response = [("success", amp.Integer())]

class OMCIDevice(child.AMPChild):
    @Activate.responder
    def activate(self, device, adapter):
        import structlog
        #from adapters.brcm_openomci_onu.brcm_openomci_onu import *
        self.log = structlog.get_logger()
        self.log.info("entering-activate-process")
        self.device = device
        main_shim = MainShim(adapter.process_parameters["args"])
        registry.register('main', main_shim)

        reactor.callLater(0, self.initAndActivate, device, adapter)
        return {"success": 1}

    @inlineCallbacks
    def initAndActivate(self, device, adapter):
        self.log = structlog.get_logger()
        self.log.debug("initializing-handler")
        self.broadcom_omci = deepcopy(OpenOmciAgentDefaults)

        self.broadcom_omci['mib-synchronizer']['state-machine'] = BrcmMibSynchronizer
        self.broadcom_omci['mib-synchronizer']['database'] = MibDbExternal
        self.broadcom_omci['omci-capabilities']['tasks']['get-capabilities'] = BrcmCapabilitiesTask 

        self.core_proxy = CoreProxy(
                kafka_proxy=None,
                default_core_topic=adapter.process_parameters["core_topic"],
                my_listening_topic=adapter.process_parameters["listening_topic"])

        self.adapter_proxy = AdapterProxy(
                kafka_proxy=None,
                core_topic=adapter.process_parameters["core_topic"],
                my_listening_topic=adapter.process_parameters["listening_topic"])

        openonu_request_handler = InterAdapterRequestFacade(adapter=self,
                                                           core_proxy=self.core_proxy)
        self.log.debug("starting-kafka-client")
        yield registry.register(
                'kafka_adapter_proxy',
                IKafkaMessagingProxy(
                    kafka_host_port=adapter.process_parameters["args"].kafka_adapter,
                    # TODO: Add KV Store object reference
                    kv_store=adapter.process_parameters["args"].backend,
                    default_topic=adapter.process_parameters["args"].name,
                    group_id_prefix=adapter.process_parameters["args"].instance_id,
                    target_cls=openonu_request_handler
                )
            ).start()

        self.core_proxy.kafka_proxy = get_messaging_proxy()
        self.adapter_proxy.kafka_proxy = get_messaging_proxy()

        self.log.debug("initializing-omci-agent")
        self.omci_agent = OpenOMCIAgent(self.core_proxy,
                                             self.adapter_proxy,
                                             support_classes=self.broadcom_omci)
        adapterShim = BrcmAdapterShim(self.core_proxy, self.adapter_proxy, self.omci_agent) 
        self.handler = BrcmOpenomciOnuHandler(adapterShim, device.id)
        self.handler.activate(device)

#    @ProcessMessage.responder
#   def processMessage(self, msg):
#        import os
#        import structlog
#        self.log.debug("sending-process-message")
#        self.handler.process_inter_adapter_message(msg)
#        millis = int(round(time.time() * 1000))
#        self.log.debug("started-process-message", millis=millis)
#        return {"success": 1}

    def process_inter_adapter_message(self, msg):
        try:
            self.log = structlog.get_logger()
            self.log.debug('process-inter-adapter-message', msg=msg)
            # Unpack the header to know which device needs to handle this message
            if msg.header:
                if self.device.id == msg.header.to_device_id:
                    self.handler.process_inter_adapter_message(msg)
        except Exception as err:
            self.log.error(err)
