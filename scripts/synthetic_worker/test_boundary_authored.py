"""AUTHORED ONLY. Do not execute/import/collect until separately qualified.

All actual fixture targets are disposable descendants of the worker directory.
No tempfile, pytest basetemp, external fixture, product import, or cleanup tree.
"""

from contextlib import ExitStack, contextmanager
import os
import unittest
from unittest import mock

import worker


@contextmanager
def no_filesystem_calls():
    """Lexical refusals must precede even a metadata read or descriptor dup."""
    with ExitStack() as stack:
        for name in ("open", "stat", "lstat", "fstat", "listdir", "scandir", "mkdir",
                     "rmdir", "unlink", "rename", "replace", "read", "write", "dup",
                     "getcwd", "chdir", "link", "symlink", "chmod", "utime"):
            stack.enter_context(mock.patch.object(
                worker.os, name, side_effect=AssertionError("unexpected I/O: " + name)
            ))
        yield


class BoundaryControls(unittest.TestCase):
    def setUp(self):
        self.run = worker.OwnedRun.create()
        self.addCleanup(self.run.close)
        self.canaries = worker.OwnedRun.create()
        self.addCleanup(self.canaries.close)
        self.good = self.run.root + "/source.bin"
        self.canary = self.canaries.root + "/canary.bin"
        self.run.write_new(self.good, b"synthetic source")
        self.canaries.write_new(self.canary, b"disposable canary")

    def refused_before_io(self, callback):
        with no_filesystem_calls():
            with self.assertRaises(worker.BoundaryError):
                callback()

    def assert_canary(self):
        self.assertEqual(self.canaries.read(self.canary), b"disposable canary")

    def test_all_public_path_operations_refuse_bad_spellings_before_io(self):
        ceiling = worker._script_ceiling()
        bad_paths = (
            "source.bin", ".", "..", self.run.root + "/../source.bin",
            self.run.root + "/./source.bin", self.run.root + "//source.bin",
            self.run.root + "/source.bin/", self.run.root + "/bad\0name",
            self.run.root + "-sibling/source.bin", ceiling + "-sibling/canary.bin",
            self.canary, ceiling + "/../canary.bin", ceiling,
            ceiling + "/worker.py", ceiling + "/README.md",
            ceiling + "/test_boundary_authored.py",
        )
        for path in bad_paths:
            operations = (
                lambda: self.run.read(path), lambda: self.run.sha256(path),
                lambda: self.run.metadata(path), lambda: self.run.list_dir(path),
                lambda: self.run.mkdir(path), lambda: self.run.write_new(path, b"x"),
                lambda: self.run.delete_file(path), lambda: self.run.remove_empty_dir(path),
                lambda: self.run.copy_file(path, self.run.root + "/copy.bin"),
                lambda: self.run.copy_file(self.good, path),
                lambda: self.run.move_file(path, self.run.root + "/move.bin"),
                lambda: self.run.move_file(self.good, path),
            )
            for index, operation in enumerate(operations):
                with self.subTest(path=path, operation=index):
                    self.refused_before_io(operation)
        self.assert_canary()

    def test_nonliteral_path_cannot_invoke_fspath(self):
        class SneakyPath:
            def __fspath__(self):
                raise AssertionError("__fspath__ must not be called")

        self.refused_before_io(lambda: self.run.read(SneakyPath()))

    def test_run_root_is_not_a_file_or_removal_target(self):
        self.refused_before_io(lambda: self.run.write_new(self.run.root, b"x"))
        self.refused_before_io(lambda: self.run.delete_file(self.run.root))
        self.refused_before_io(lambda: self.run.remove_empty_dir(self.run.root))

    def test_healthy_operations_and_no_overwrite(self):
        folder = self.run.root + "/nested"
        self.run.mkdir(folder)
        empty = folder + "/empty"
        self.run.mkdir(empty)
        self.run.remove_empty_dir(empty)
        copy = folder + "/copy.bin"
        moved = folder + "/moved.bin"
        self.run.copy_file(self.good, copy)
        self.assertEqual(self.run.read(copy), b"synthetic source")
        self.assertEqual(self.run.sha256(copy), self.run.sha256(self.good))
        self.assertEqual(self.run.metadata(copy)["links"], 1)
        self.assertEqual(self.run.list_dir(folder), ["copy.bin"])
        self.run.move_file(copy, moved)
        with self.assertRaises(FileNotFoundError):
            self.run.read(copy)
        for operation in (
            lambda: self.run.write_new(moved, b"overwrite"),
            lambda: self.run.copy_file(self.good, moved),
            lambda: self.run.move_file(self.good, moved),
        ):
            with self.assertRaises((worker.BoundaryError, FileExistsError)):
                operation()
        self.assertEqual(self.run.read(moved), b"synthetic source")
        self.run.delete_file(moved)
        self.run.remove_empty_dir(folder)
        self.assertEqual(self.run.list_dir(self.run.root), ["source.bin"])
        self.assert_canary()

    def test_fresh_claim_cannot_reuse_existing_run(self):
        with self.assertRaises(FileExistsError):
            worker.OwnedRun.create(self.run._name)
        self.assertEqual(self.run.read(self.good), b"synthetic source")

    def test_run_name_cannot_choose_root_or_source_files(self):
        for name in ("../run-escape", "run-x/nested", "README.md", self.run.root,
                     "run-", "run-..", "run-SPACE ", "run-x\0"):
            with self.subTest(name=name):
                self.refused_before_io(lambda: worker.OwnedRun.create(name))

    def test_cwd_and_environment_do_not_select_ceiling(self):
        # No actual cwd change: make any attempt to consult it fail immediately.
        with mock.patch.object(worker.os, "getcwd", side_effect=AssertionError("cwd")):
            with mock.patch.dict(os.environ, {
                "HOME": self.canaries.root, "TMPDIR": self.canaries.root,
                "SYNTHETIC_WORKER_ROOT": self.canaries.root,
                "RAWDOG_REPOSITORY": self.canaries.root,
            }):
                run = worker.OwnedRun.create()
                try:
                    self.assertEqual(run.root.rsplit("/", 1)[0], worker._script_ceiling())
                finally:
                    run.close()
                self.refused_before_io(lambda: self.run.read("source.bin"))

    def test_relative_or_aliased_script_spellings_refused_before_io(self):
        # Source-location admission never repairs spellings using cwd/resolve.
        for spelling in ("worker.py", "scripts/synthetic_worker/worker.py",
                         self.canaries.root + "/scripts/synthetic_worker/worker.py",
                         worker._script_ceiling() + "/../synthetic_worker/worker.py"):
            with self.subTest(spelling=spelling):
                with mock.patch.object(worker, "__file__", spelling):
                    self.refused_before_io(lambda: worker.OwnedRun.create("run-control"))

    def test_bootstrap_nofollow_failure_precedes_run_creation(self):
        # Do not replace real repository directories. Simulate kernel rejection
        # of each canonical bootstrap component, and prove no mkdir follows.
        for failure_index in (0, 1, 2):
            calls = []

            def open_component(path, flags, **kwargs):
                self.assertTrue(flags & os.O_NOFOLLOW)
                self.assertTrue(flags & os.O_DIRECTORY)
                calls.append((path, kwargs.get("dir_fd")))
                if len(calls) == failure_index + 1:
                    raise OSError("simulated symlink component refusal")
                return 100 + len(calls)

            with mock.patch.object(worker.os, "open", side_effect=open_component):
                with mock.patch.object(worker.os, "close"):
                    with mock.patch.object(worker.os, "mkdir", side_effect=AssertionError("mkdir")):
                        with self.assertRaises(OSError):
                            worker.OwnedRun.create("run-bootstrap-control")
            self.assertEqual(calls, [
                (worker._ADMITTED_CHECKOUT, None), ("scripts", 101),
                ("synthetic_worker", 102),
            ][:failure_index + 1])

    def test_live_and_dangling_leaf_links_are_never_followed(self):
        for name, target in (("live", self.canary), ("dangling", self.canaries.root + "/absent")):
            # Direct fixture syscall: destination is this owned run descriptor;
            # target spelling is another disposable run inside the same ceiling.
            os.symlink(target, name, dir_fd=self.run._fd)
            path = self.run.root + "/" + name
            try:
                for operation in (
                    lambda: self.run.read(path), lambda: self.run.sha256(path),
                    lambda: self.run.metadata(path), lambda: self.run.list_dir(path),
                    lambda: self.run.write_new(path, b"mutate canary"),
                    lambda: self.run.delete_file(path), lambda: self.run.remove_empty_dir(path),
                    lambda: self.run.copy_file(path, self.run.root + "/copy-" + name),
                    lambda: self.run.copy_file(self.good, path),
                    lambda: self.run.move_file(path, self.run.root + "/move-" + name),
                    lambda: self.run.move_file(self.good, path),
                    lambda: self.run.list_dir(self.run.root),
                ):
                    with self.subTest(name=name, operation=operation):
                        with self.assertRaises((worker.BoundaryError, OSError)):
                            operation()
                self.assert_canary()
            finally:
                os.unlink(name, dir_fd=self.run._fd)  # Fixture link only; no target access.

    def test_live_and_dangling_ancestor_links_refuse_both_endpoints(self):
        for name, target in (("live-dir", self.canaries.root),
                             ("dangling-dir", self.canaries.root + "/missing-dir")):
            os.symlink(target, name, dir_fd=self.run._fd)
            path = self.run.root + "/" + name + "/canary.bin"
            try:
                for operation in (
                    lambda: self.run.read(path), lambda: self.run.sha256(path),
                    lambda: self.run.metadata(path), lambda: self.run.list_dir(path),
                    lambda: self.run.mkdir(path), lambda: self.run.write_new(path, b"x"),
                    lambda: self.run.delete_file(path), lambda: self.run.remove_empty_dir(path),
                    lambda: self.run.copy_file(path, self.run.root + "/copy-" + name),
                    lambda: self.run.copy_file(self.good, path),
                    lambda: self.run.move_file(path, self.run.root + "/move-" + name),
                    lambda: self.run.move_file(self.good, path),
                ):
                    with self.subTest(name=name, operation=operation):
                        with self.assertRaises((worker.BoundaryError, OSError)):
                            operation()
                self.assert_canary()
            finally:
                os.unlink(name, dir_fd=self.run._fd)

    def test_hard_links_cannot_be_read_or_mutated_through_boundary(self):
        os.link("canary.bin", "hard-link", src_dir_fd=self.canaries._fd,
                dst_dir_fd=self.run._fd, follow_symlinks=False)
        path = self.run.root + "/hard-link"
        try:
            for operation in (
                lambda: self.run.read(path), lambda: self.run.sha256(path),
                lambda: self.run.metadata(path), lambda: self.run.list_dir(self.run.root),
                lambda: self.run.delete_file(path), lambda: self.run.write_new(path, b"x"),
                lambda: self.run.copy_file(path, self.run.root + "/hard-copy"),
                lambda: self.run.move_file(path, self.run.root + "/hard-move"),
                lambda: self.run.copy_file(self.good, path),
                lambda: self.run.move_file(self.good, path),
            ):
                with self.assertRaises((worker.BoundaryError, FileExistsError)):
                    operation()
        finally:
            os.unlink("hard-link", dir_fd=self.run._fd)
        self.assert_canary()

    def test_replaced_run_root_refused_without_following_link(self):
        # Simulate replacement instead of renaming any top-level run directory.
        replacement_directory = os.fstat(self.canaries._fd)
        replacement_link = os.stat_result((worker.stat.S_IFLNK | 0o777, 0, 0, 1,
                                            0, 0, 0, 0, 0, 0))
        for replacement in (replacement_directory, replacement_link):
            with mock.patch.object(worker.os, "stat", return_value=replacement) as check:
                with mock.patch.object(worker.os, "open", side_effect=AssertionError("open")):
                    with self.assertRaises(worker.BoundaryError):
                        self.run.write_new(self.run.root + "/must-not-exist", b"x")
                check.assert_called_once_with(self.run._name, dir_fd=self.run._ceiling_fd,
                                               follow_symlinks=False)
        self.assert_canary()

    def test_closed_capability_refuses_operations(self):
        self.run.close()
        with self.assertRaises(worker.BoundaryError):
            self.run.read(self.good)


class EntryControls(unittest.TestCase):
    def test_entry_is_unconditionally_blocked(self):
        with mock.patch.dict(os.environ, {"RAWDOG_RUNTIME_QUALIFIED": "1",
                                          "SYNTHETIC_WORKER_APPROVED": "1"}):
            with mock.patch.object(worker.sys, "argv", ["worker.py", "--force", "--receipt=approved"]):
                with mock.patch.object(worker.OwnedRun, "create", side_effect=AssertionError("run")):
                    with mock.patch.object(worker.sys.stderr, "write") as output:
                        with no_filesystem_calls():
                            self.assertEqual(worker.main(), 78)
                        self.assertIn("BLOCKED", output.call_args.args[0])


if __name__ == "__main__":
    raise SystemExit("BLOCKED: these controls are authored only; runtime qualification is required")
