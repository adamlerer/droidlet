"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import logging
import os
import random
import re
import time
import numpy as np

from agents.core import BaseAgent
from droidlet.shared_data_structs import ErrorWithResponse
from droidlet.event import sio

from droidlet.base_util import hash_user
from droidlet.memory.save_and_fetch_commands import *

random.seed(0)

DATABASE_FILE_FOR_DASHBOARD = "dashboard_data.db"
DEFAULT_BEHAVIOUR_TIMEOUT = 20
MEMORY_DUMP_KEYFRAME_TIME = 0.5
# a BaseAgent with:
# 1: a controller that is (mostly) a dialogue manager, and the dialogue manager
#      is powered by a neural semantic parser.
# 2: has a turnable head, can point, and has basic locomotion
# 3: can send and receive chats

# this name is pathetic please help
class LocoMCAgent(BaseAgent):
    def __init__(self, opts, name=None):
        logging.info("Agent.__init__ started")
        self.name = name or default_agent_name()
        self.opts = opts
        self.init_physical_interfaces()
        super(LocoMCAgent, self).__init__(opts, name=self.name)
        self.uncaught_error_count = 0
        self.last_chat_time = 0
        self.last_task_memid = None
        self.dashboard_chat = None
        self.areas_to_perceive = []
        self.perceive_on_chat = False
        self.dashboard_memory_dump_time = time.time()
        self.dashboard_memory = {
            "db": {},
            "objects": [],
            "humans": [],
            "chatResponse": {},
            "chats": [
                {"msg": "", "failed": False},
                {"msg": "", "failed": False},
                {"msg": "", "failed": False},
                {"msg": "", "failed": False},
                {"msg": "", "failed": False},
            ],
        }

    def init_event_handlers(self):
        ## emit event from statemanager and send dashboard memory from here
        # create a connection to database file
        logging.info("creating the connection to db file: %r" % (DATABASE_FILE_FOR_DASHBOARD))
        self.conn = create_connection(DATABASE_FILE_FOR_DASHBOARD)
        # create all tables if they don't already exist
        logging.info("creating all tables for Visual programming and error annotation ...")
        create_all_tables(self.conn)

        @sio.on("saveCommand")
        def save_command_to_db(sid, postData):
            print("in save_command_to_db, got postData: %r" % (postData))
            # save the command and fetch all
            out = saveAndFetchCommands(self.conn, postData)
            if out == "DUPLICATE":
                print("Duplicate command not saved.")
            else:
                print("Saved successfully")
            payload = {"commandList": out}
            sio.emit("updateSearchList", payload)

        @sio.on("fetchCommand")
        def get_cmds_from_db(sid, postData):
            print("in get_cmds_from_db, got postData: %r" % (postData))
            out = onlyFetchCommands(self.conn, postData["query"])
            payload = {"commandList": out}
            sio.emit("updateSearchList", payload)

        @sio.on("saveErrorDetailsToDb")
        def save_error_details_to_db(sid, postData):
            logging.debug("in save_error_details_to_db, got PostData: %r" % (postData))
            # save the details to table
            saveAnnotatedErrorToDb(self.conn, postData)

        @sio.on("saveSurveyInfo")
        def save_survey_info_to_db(sid, postData):
            logging.debug("in save_survey_info_to_db, got PostData: %r" % (postData))
            # save details to survey table
            saveSurveyResultsToDb(self.conn, postData)

        @sio.on("saveObjectAnnotation")
        def save_object_annotation_to_db(sid, postData):
            logging.debug("in save_object_annotation_to_db, got postData: %r" % (postData))
            saveObjectAnnotationsToDb(self.conn, postData)

        @sio.on("sendCommandToAgent")
        def send_text_command_to_agent(sid, command):
            """Add the command to agent's incoming chats list and
            send back the parse.
            Args:
                command: The input text command from dashboard player
            Returns:
                return back a socket emit with parse of command and success status
            """
            logging.debug("in send_text_command_to_agent, got the command: %r" % (command))
            agent_chat = (
                "<dashboard> " + command
            )  # the chat is coming from a player called "dashboard"
            self.dashboard_chat = agent_chat
            dialogue_manager = self.dialogue_manager
            logical_form = {}
            status = ""
            try:
                logical_form = dialogue_manager.semantic_parsing_model_wrapper.get_logical_form(
                    chat=command, parsing_model=dialogue_manager.semantic_parsing_model_wrapper.parsing_model
                )
                logging.debug("logical form is : %r" % (logical_form))
                status = "Sent successfully"
            except Exception as e:
                logging.error("error in sending chat", e)
                status = "Error in sending chat"
            # update server memory
            self.dashboard_memory["chatResponse"][command] = logical_form
            self.dashboard_memory["chats"].pop(0)
            self.dashboard_memory["chats"].append({"msg": command, "failed": False})
            payload = {
                "status": status,
                "chat": command,
                "chatResponse": self.dashboard_memory["chatResponse"][command],
                "allChats": self.dashboard_memory["chats"],
            }
            sio.emit("setChatResponse", payload)

        @sio.on("receiveTimelineHandshake")
        def receive_timeline_handshake(sid, timelineHandshake):
            if timelineHandshake == "Sent message!":
                logging.debug("in receive_timeline_handshake, received handshake message")
                sio.emit("returnTimelineHandshake", "Received message!")

    def init_physical_interfaces(self):
        """
        should define or otherwise set up
        (at least):
        self.send_chat(),
        movement primitives, including
        self.look_at(x, y, z):
        self.set_look(look):
        self.point_at(...),
        self.relative_head_pitch(angle)
        ...
        """
        raise NotImplementedError

    def init_perception(self):
        """
        should define (at least):
        self.get_pos()
        self.get_incoming_chats()
        and the perceptual modules that write to memory
        all modules that should write to memory on a perceive() call
        should be registered in self.perception_modules, and have
        their own .perceive() fn
        """
        raise NotImplementedError

    def init_memory(self):
        """something like:
        self.memory = memory.AgentMemory(
            db_file=os.environ.get("DB_FILE", ":memory:"),
            db_log_path="agent_memory.{}.log".format(self.name),
        )
        """
        raise NotImplementedError

    def init_controller(self):
        """
        dialogue_object_classes["interpreter"] = ....
        dialogue_object_classes["get_memory"] = ....
        dialogue_object_classes["put_memory"] = ....
        self.dialogue_manager = DialogueManager(self,
                                                   dialogue_object_classes,
                                                   self.opts)
        logging.info("Initialized DialogueManager")
        """
        raise NotImplementedError

    def handle_exception(self, e):
        logging.exception(
            "Default handler caught exception, db_log_idx={}".format(self.memory.get_db_log_idx())
        )

        # we check if the exception raised is in one of our whitelisted exceptions
        # if so, we raise a reasonable message to the user, and then do some clean
        # up and continue
        if isinstance(e, ErrorWithResponse):
            self.send_chat("Oops! Ran into an exception.\n'{}''".format(e.chat))
            self.memory.task_stack_clear()
            self.dialogue_manager.dialogue_stack.clear()
            self.uncaught_error_count += 1
            if self.uncaught_error_count >= 100:
                raise e
        else:
            # if it's not a whitelisted exception, immediatelly raise upwards,
            # unless you are in some kind of a debug mode
            if self.opts.agent_debug_mode:
                return
            else:
                raise e

    def step(self):
        if self.count == 0:
            logging.debug("First top-level step()")
        super().step()
        self.maybe_dump_memory_to_dashboard()

    def task_step(self, sleep_time=0.25):
        query = {"base_table": "Tasks", "base_exact": {"prio": -1}}
        task_mems = self.memory.basic_search(query)
        for mem in task_mems:
            if mem.task.init_condition.check():
                mem.get_update_status({"prio": 0})

        # this is "select TaskNodes whose priority is >= 0 and are not paused"
        query = {"base_table": "Tasks", "base_range": {"minprio": -0.5, "maxpaused": 0.5}}
        task_mems = self.memory.basic_search(query)
        for mem in task_mems:
            if mem.task.run_condition.check():
                # eventually we need to use the multiplex filter to decide what runs
                mem.get_update_status({"prio": 1, "running": 1})
            if mem.task.stop_condition.check():
                mem.get_update_status({"prio": 0, "running": 0})
        # this is "select TaskNodes that are runnning (running >= 1) and are not paused"
        query = {"base_table": "Tasks", "base_range": {"minrunning": 0.5, "maxpaused": 0.5}}
        task_mems = self.memory.basic_search(query)
        if not task_mems:
            time.sleep(sleep_time)
            return
        for mem in task_mems:
            mem.task.step()
            if mem.task.finished:
                mem.update_task()

    def get_time(self):
        # round to 100th of second, return as
        # n hundreth of seconds since agent init
        return self.memory.get_time()

    def perceive(self, force=False):
        for v in self.perception_modules.values():
            v.perceive(force=force)

    def controller_step(self):
        # FIXME agent these should be moved to perception
        # from here ###########################################
        """Process incoming chats and modify task stack"""
        raw_incoming_chats = self.get_incoming_chats()
        if raw_incoming_chats:
            logging.info("Incoming chats: {}".format(raw_incoming_chats))
        incoming_chats = []
        for raw_chat in raw_incoming_chats:
            match = re.search("^<([^>]+)> (.*)", raw_chat)
            if match is None:
                logging.debug("Ignoring chat: {}".format(raw_chat))
                continue

            speaker, chat = match.group(1), match.group(2)
            speaker_hash = hash_user(speaker)
            logging.debug("Incoming chat: ['{}' -> {}]".format(speaker_hash, chat))
            if chat.startswith("/"):
                continue
            incoming_chats.append((speaker, chat))
            self.memory.add_chat(self.memory.get_player_by_name(speaker).memid, chat)

        if len(incoming_chats) > 0:
            # force to get objects, speaker info
            if self.perceive_on_chat:
                self.perceive(force=True)
            # change this to memory.get_time() format?
            self.last_chat_time = time.time()
            # to here ###########################################
            # for now just process the first incoming chat
            self.dialogue_manager.step(incoming_chats[0])
        else:
            # Maybe add default task
            if not self.no_default_behavior:
                self.maybe_run_slow_defaults()
            self.dialogue_manager.step((None, ""))

        # Always call dialogue_stack.step(), even if chat is empty
        if len(self.memory.dialogue_stack) > 0:
            self.memory.dialogue_stack.step(self)

    def maybe_run_slow_defaults(self):
        """Pick a default task task to run
        with a low probability"""
        if self.memory.task_stack_peek() or len(self.dialogue_manager.dialogue_stack) > 0:
            return

        # default behaviors of the agent not visible in the game
        invisible_defaults = []

        defaults = (
            self.visible_defaults + invisible_defaults
            if time.time() - self.last_chat_time > DEFAULT_BEHAVIOUR_TIMEOUT
            else invisible_defaults
        )

        defaults = [(p, f) for (p, f) in defaults if f not in self.memory.banned_default_behaviors]

        def noop(*args):
            pass

        defaults.append((1 - sum(p for p, _ in defaults), noop))  # noop with remaining prob

        # weighted random choice of functions
        p, fns = zip(*defaults)
        fn = np.random.choice(fns, p=p)
        if fn != noop:
            logging.debug("Default behavior: {}".format(fn))
        fn(self)

    def maybe_dump_memory_to_dashboard(self):
        if time.time() - self.dashboard_memory_dump_time > MEMORY_DUMP_KEYFRAME_TIME:
            self.dashboard_memory_dump_time = time.time()
            memories_main = self.memory._db_read("SELECT * FROM Memories")
            triples = self.memory._db_read("SELECT * FROM Triples")
            reference_objects = self.memory._db_read("SELECT * FROM ReferenceObjects")
            named_abstractions = self.memory._db_read("SELECT * FROM NamedAbstractions")
            self.dashboard_memory["db"] = {
                "memories": memories_main,
                "triples": triples,
                "reference_objects": reference_objects,
                "named_abstractions": named_abstractions,
            }
            sio.emit("memoryState", self.dashboard_memory["db"])


def default_agent_name():
    """Use a unique name based on timestamp"""
    return "bot.{}".format(str(time.time())[3:13])
