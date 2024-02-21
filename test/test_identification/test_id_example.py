from shutil import which, rmtree
import tempfile
import logging
import time
import unittest
from threading import Thread

import read_until.examples.identification

from ..test_utils import run_server
from ..read_until_test_server import ReadUntilTestServer
from .id_test_server import DataService, DIR


class TestBaseCallModule(unittest.TestCase):
    def setUp(self):
        logging.basicConfig(level=logging.DEBUG)
        self.GUPPY_EXEC = which("dorado_basecall_server")
        if self.GUPPY_EXEC is None:
            self.skipTest("dorado_basecall_server not found")

        self.log_path = tempfile.mkdtemp()
        self.config = "dna_r9.4.1_450bps_fast.cfg"

        opts = [
            "--config",
            self.config,
            "--port",
            "auto",
            "--log_path",
            self.log_path,
            "--disable_pings",
        ]

        self.guppy_server, self.guppy_port = run_server(self.GUPPY_EXEC, opts)

        self.minknow_server = ReadUntilTestServer(data_service=DataService)
        self.minknow_port = self.minknow_server.port
        self.minknow_server.start()
        self.mmi_path = str(DIR / "test_ref.mmi")
        logging.debug("guppy on: {}".format(self.guppy_port))

        if not self.guppy_port:
            self.skipTest("Guppy port was 0")

        # Allow servers time to start up
        time.sleep(2)

    def tearDown(self):
        self.minknow_server.stop(0)
        self.guppy_server.stdout.close()
        self.guppy_server.kill()
        self.guppy_server.wait()
        rmtree(self.log_path)

    def test_identification(self):
        def run_main(gport, mport):
            read_until.examples.identification.main(
                [
                    "--port",
                    str(mport),
                    "--ca-cert",
                    str(self.minknow_server.ca_cert_path),
                    "--guppy_port",
                    str(gport),
                    "--run_time",
                    "60",
                    "--align",
                    self.mmi_path,
                ]
            )

        run_thread = Thread(target=run_main, args=(self.guppy_port, self.minknow_port))
        run_thread.start()

        run_thread.join()

        assert self.minknow_server.data_service.sent_reads > 0
        assert self.minknow_server.data_service.stop_count > 0
        assert self.minknow_server.data_service.unblock_count > 0


if __name__ == "__main__":
    unittest.main()
