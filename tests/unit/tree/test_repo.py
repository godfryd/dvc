import os
import shutil
from unittest import mock

import pytest

from dvc.hash_info import HashInfo
from dvc.path_info import PathInfo
from dvc.tree.repo import RepoTree


def test_exists(tmp_dir, dvc):
    tmp_dir.gen("foo", "foo")
    dvc.add("foo")
    (tmp_dir / "foo").unlink()

    tree = RepoTree(dvc)
    assert tree.exists("foo")


def test_open(tmp_dir, dvc):
    tmp_dir.gen("foo", "foo")
    dvc.add("foo")
    (tmp_dir / "foo").unlink()

    tree = RepoTree(dvc)
    with tree.open("foo", "r") as fobj:
        assert fobj.read() == "foo"


def test_open_dirty_hash(tmp_dir, dvc):
    tmp_dir.dvc_gen("file", "file")
    (tmp_dir / "file").write_text("something")

    tree = RepoTree(dvc)
    with tree.open("file", "r") as fobj:
        assert fobj.read() == "something"


def test_open_dirty_no_hash(tmp_dir, dvc):
    tmp_dir.gen("file", "file")
    (tmp_dir / "file.dvc").write_text("outs:\n- path: file\n")

    tree = RepoTree(dvc)
    with tree.open("file", "r") as fobj:
        assert fobj.read() == "file"


def test_open_in_history(tmp_dir, scm, dvc):
    tmp_dir.gen("foo", "foo")
    dvc.add("foo")
    dvc.scm.add(["foo.dvc", ".gitignore"])
    dvc.scm.commit("foo")

    tmp_dir.gen("foo", "foofoo")
    dvc.add("foo")
    dvc.scm.add(["foo.dvc", ".gitignore"])
    dvc.scm.commit("foofoo")

    for rev in dvc.brancher(revs=["HEAD~1"]):
        if rev == "workspace":
            continue

        tree = RepoTree(dvc)
        with tree.open("foo", "r") as fobj:
            assert fobj.read() == "foo"


def test_isdir_isfile(tmp_dir, dvc):
    tmp_dir.gen({"datafile": "data", "datadir": {"foo": "foo", "bar": "bar"}})

    tree = RepoTree(dvc)
    assert tree.isdir("datadir")
    assert not tree.isfile("datadir")
    assert not tree.isdvc("datadir")
    assert not tree.isdir("datafile")
    assert tree.isfile("datafile")
    assert not tree.isdvc("datafile")

    dvc.add(["datadir", "datafile"])
    shutil.rmtree(tmp_dir / "datadir")
    (tmp_dir / "datafile").unlink()

    assert tree.isdir("datadir")
    assert not tree.isfile("datadir")
    assert tree.isdvc("datadir")
    assert not tree.isdir("datafile")
    assert tree.isfile("datafile")
    assert tree.isdvc("datafile")


def test_exists_isdir_isfile_dirty(tmp_dir, dvc):
    tmp_dir.dvc_gen(
        {"datafile": "data", "datadir": {"foo": "foo", "bar": "bar"}}
    )

    tree = RepoTree(dvc, stream=True)
    shutil.rmtree(tmp_dir / "datadir")
    (tmp_dir / "datafile").unlink()

    root = PathInfo(tmp_dir)
    assert tree.exists(root / "datafile")
    assert tree.exists(root / "datadir")
    assert tree.exists(root / "datadir" / "foo")
    assert tree.isfile(root / "datafile")
    assert not tree.isfile(root / "datadir")
    assert tree.isfile(root / "datadir" / "foo")
    assert not tree.isdir(root / "datafile")
    assert tree.isdir(root / "datadir")
    assert not tree.isdir(root / "datadir" / "foo")

    # NOTE: creating file instead of dir and dir instead of file
    tmp_dir.gen({"datadir": "data", "datafile": {"foo": "foo", "bar": "bar"}})
    assert tree.exists(root / "datafile")
    assert tree.exists(root / "datadir")
    assert not tree.exists(root / "datadir" / "foo")
    assert tree.exists(root / "datafile" / "foo")
    assert not tree.isfile(root / "datafile")
    assert tree.isfile(root / "datadir")
    assert not tree.isfile(root / "datadir" / "foo")
    assert tree.isfile(root / "datafile" / "foo")
    assert tree.isdir(root / "datafile")
    assert not tree.isdir(root / "datadir")
    assert not tree.isdir(root / "datadir" / "foo")
    assert not tree.isdir(root / "datafile" / "foo")


def test_isdir_mixed(tmp_dir, dvc):
    tmp_dir.gen({"dir": {"foo": "foo", "bar": "bar"}})

    dvc.add(str(tmp_dir / "dir" / "foo"))

    tree = RepoTree(dvc)
    assert tree.isdir("dir")
    assert not tree.isfile("dir")


@pytest.mark.parametrize(
    "dvcfiles,extra_expected",
    [
        (False, []),
        (
            True,
            [
                PathInfo("dir") / "subdir1" / "foo1.dvc",
                PathInfo("dir") / "subdir1" / "bar1.dvc",
                PathInfo("dir") / "subdir2" / "foo2.dvc",
            ],
        ),
    ],
)
def test_walk(tmp_dir, dvc, dvcfiles, extra_expected):
    tmp_dir.gen(
        {
            "dir": {
                "subdir1": {"foo1": "foo1", "bar1": "bar1"},
                "subdir2": {"foo2": "foo2"},
            }
        }
    )
    dvc.add(str(tmp_dir / "dir"), recursive=True)
    tmp_dir.gen({"dir": {"foo": "foo", "bar": "bar"}})
    tree = RepoTree(dvc)

    expected = [
        PathInfo("dir") / "subdir1",
        PathInfo("dir") / "subdir2",
        PathInfo("dir") / "subdir1" / "foo1",
        PathInfo("dir") / "subdir1" / "bar1",
        PathInfo("dir") / "subdir2" / "foo2",
        PathInfo("dir") / "foo",
        PathInfo("dir") / "bar",
    ]

    actual = []
    for root, dirs, files in tree.walk("dir", dvcfiles=dvcfiles):
        for entry in dirs + files:
            actual.append(os.path.join(root, entry))

    expected = [str(path) for path in expected + extra_expected]
    assert set(actual) == set(expected)
    assert len(actual) == len(expected)


def test_walk_dirty(tmp_dir, dvc):
    tmp_dir.dvc_gen(
        {
            "dir": {
                "foo": "foo",
                "subdir1": {"foo1": "foo1", "bar1": "bar1"},
                "subdir2": {"foo2": "foo2"},
            }
        }
    )
    tmp_dir.gen({"dir": {"bar": "bar", "subdir3": {"foo3": "foo3"}}})
    (tmp_dir / "dir" / "foo").unlink()

    tree = RepoTree(dvc)
    expected = [
        PathInfo("dir") / "subdir1",
        PathInfo("dir") / "subdir2",
        PathInfo("dir") / "subdir3",
        PathInfo("dir") / "subdir1" / "foo1",
        PathInfo("dir") / "subdir1" / "bar1",
        PathInfo("dir") / "subdir2" / "foo2",
        PathInfo("dir") / "subdir3" / "foo3",
        PathInfo("dir") / "bar",
    ]

    actual = []
    for root, dirs, files in tree.walk("dir"):
        for entry in dirs + files:
            actual.append(os.path.join(root, entry))

    expected = [str(path) for path in expected]
    assert set(actual) == set(expected)
    assert len(actual) == len(expected)


def test_walk_dirty_cached_dir(tmp_dir, scm, dvc):
    tmp_dir.dvc_gen(
        {"data": {"foo": "foo", "bar": "bar"}}, commit="add data",
    )
    (tmp_dir / "data" / "foo").unlink()

    tree = RepoTree(dvc)

    data = PathInfo(tmp_dir) / "data"

    actual = []
    for root, dirs, files in tree.walk(data):
        for entry in dirs + files:
            actual.append(os.path.join(root, entry))

    assert actual == [(data / "bar").fspath]


def test_walk_mixed_dir(tmp_dir, scm, dvc):
    tmp_dir.gen({"dir": {"foo": "foo", "bar": "bar"}})
    tmp_dir.dvc.add(os.path.join("dir", "foo"))
    tmp_dir.scm.add(
        [
            os.path.join("dir", "bar"),
            os.path.join("dir", ".gitignore"),
            os.path.join("dir", "foo.dvc"),
        ]
    )
    tmp_dir.scm.commit("add dir")

    tree = RepoTree(dvc)

    expected = [
        str(PathInfo("dir") / "foo"),
        str(PathInfo("dir") / "bar"),
        str(PathInfo("dir") / ".gitignore"),
    ]
    actual = []
    for root, dirs, files in tree.walk("dir"):
        for entry in dirs + files:
            actual.append(os.path.join(root, entry))

    assert set(actual) == set(expected)
    assert len(actual) == len(expected)


def test_walk_onerror(tmp_dir, dvc):
    def onerror(exc):
        raise exc

    tmp_dir.dvc_gen("foo", "foo")
    tree = RepoTree(dvc)

    # path does not exist
    for _ in tree.walk("dir"):
        pass
    with pytest.raises(OSError):
        for _ in tree.walk("dir", onerror=onerror):
            pass

    # path is not a directory
    for _ in tree.walk("foo"):
        pass
    with pytest.raises(OSError):
        for _ in tree.walk("foo", onerror=onerror):
            pass


def test_isdvc(tmp_dir, dvc):
    tmp_dir.gen({"foo": "foo", "bar": "bar", "dir": {"baz": "baz"}})
    dvc.add("foo")
    dvc.add("dir")
    tree = RepoTree(dvc)
    assert tree.isdvc("foo")
    assert not tree.isdvc("bar")
    assert tree.isdvc("dir")
    assert not tree.isdvc("dir/baz")
    assert tree.isdvc("dir/baz", recursive=True)


def make_subrepo(dir_, scm, config=None):
    dir_.mkdir(parents=True, exist_ok=True)
    with dir_.chdir():
        dir_.scm = scm
        dir_.init(dvc=True, subdir=True)
        if config:
            dir_.add_remote(config=config)


def test_subrepos(tmp_dir, scm, dvc):
    tmp_dir.scm_gen(
        {"dir": {"repo.txt": "file to confuse RepoTree"}},
        commit="dir/repo.txt",
    )

    subrepo1 = tmp_dir / "dir" / "repo"
    subrepo2 = tmp_dir / "dir" / "repo2"

    for repo in [subrepo1, subrepo2]:
        make_subrepo(repo, scm)

    subrepo1.dvc_gen({"foo": "foo", "dir1": {"bar": "bar"}}, commit="FOO")
    subrepo2.dvc_gen(
        {"lorem": "lorem", "dir2": {"ipsum": "ipsum"}}, commit="BAR"
    )

    dvc.tree._reset()
    tree = RepoTree(dvc, subrepos=True, fetch=True)

    def assert_tree_belongs_to_repo(ret_val):
        method = tree._get_repo

        def f(*args, **kwargs):
            r = method(*args, **kwargs)
            assert r.root_dir == ret_val.root_dir
            return r

        return f

    with mock.patch.object(
        tree,
        "_get_repo",
        side_effect=assert_tree_belongs_to_repo(subrepo1.dvc),
    ):
        assert tree.exists(subrepo1 / "foo") is True
        assert tree.exists(subrepo1 / "bar") is False

        assert tree.isfile(subrepo1 / "foo") is True
        assert tree.isfile(subrepo1 / "dir1" / "bar") is True
        assert tree.isfile(subrepo1 / "dir1") is False

        assert tree.isdir(subrepo1 / "dir1") is True
        assert tree.isdir(subrepo1 / "dir1" / "bar") is False
        assert tree.isdvc(subrepo1 / "foo") is True

    with mock.patch.object(
        tree,
        "_get_repo",
        side_effect=assert_tree_belongs_to_repo(subrepo2.dvc),
    ):
        assert tree.exists(subrepo2 / "lorem") is True
        assert tree.exists(subrepo2 / "ipsum") is False

        assert tree.isfile(subrepo2 / "lorem") is True
        assert tree.isfile(subrepo2 / "dir2" / "ipsum") is True
        assert tree.isfile(subrepo2 / "dir2") is False

        assert tree.isdir(subrepo2 / "dir2") is True
        assert tree.isdir(subrepo2 / "dir2" / "ipsum") is False
        assert tree.isdvc(subrepo2 / "lorem") is True


@pytest.mark.parametrize(
    "dvcfiles,extra_expected",
    [
        (False, []),
        (
            True,
            [
                PathInfo("dir") / "repo" / "foo.dvc",
                PathInfo("dir") / "repo" / "dir1.dvc",
                PathInfo("dir") / "repo2" / "lorem.dvc",
                PathInfo("dir") / "repo2" / "dir2.dvc",
            ],
        ),
    ],
)
def test_subrepo_walk(tmp_dir, scm, dvc, dvcfiles, extra_expected):
    tmp_dir.scm_gen(
        {"dir": {"repo.txt": "file to confuse RepoTree"}},
        commit="dir/repo.txt",
    )

    subrepo1 = tmp_dir / "dir" / "repo"
    subrepo2 = tmp_dir / "dir" / "repo2"

    subdirs = [subrepo1, subrepo2]
    for dir_ in subdirs:
        make_subrepo(dir_, scm)

    subrepo1.dvc_gen({"foo": "foo", "dir1": {"bar": "bar"}}, commit="FOO")
    subrepo2.dvc_gen(
        {"lorem": "lorem", "dir2": {"ipsum": "ipsum"}}, commit="BAR"
    )

    # using tree that does not have dvcignore
    dvc.tree._reset()
    tree = RepoTree(dvc, subrepos=True, fetch=True)
    expected = [
        PathInfo("dir") / "repo",
        PathInfo("dir") / "repo.txt",
        PathInfo("dir") / "repo2",
        PathInfo("dir") / "repo" / ".dvcignore",
        PathInfo("dir") / "repo" / ".gitignore",
        PathInfo("dir") / "repo" / "foo",
        PathInfo("dir") / "repo" / "dir1",
        PathInfo("dir") / "repo" / "dir1" / "bar",
        PathInfo("dir") / "repo2" / ".dvcignore",
        PathInfo("dir") / "repo2" / ".gitignore",
        PathInfo("dir") / "repo2" / "lorem",
        PathInfo("dir") / "repo2" / "dir2",
        PathInfo("dir") / "repo2" / "dir2" / "ipsum",
    ]

    actual = []
    for root, dirs, files in tree.walk("dir", dvcfiles=dvcfiles):
        for entry in dirs + files:
            actual.append(os.path.join(root, entry))

    expected = [str(path) for path in expected + extra_expected]
    assert set(actual) == set(expected)
    assert len(actual) == len(expected)


def test_repo_tree_no_subrepos(tmp_dir, dvc, scm):
    tmp_dir.scm_gen(
        {"dir": {"repo.txt": "file to confuse RepoTree"}},
        commit="dir/repo.txt",
    )
    tmp_dir.dvc_gen({"lorem": "lorem"}, commit="add foo")

    subrepo = tmp_dir / "dir" / "repo"
    make_subrepo(subrepo, scm)
    subrepo.dvc_gen({"foo": "foo", "dir1": {"bar": "bar"}}, commit="FOO")
    subrepo.scm_gen({"ipsum": "ipsum"}, commit="BAR")

    # using tree that does not have dvcignore
    dvc.tree._reset()
    tree = RepoTree(dvc, subrepos=False, fetch=True)
    expected = [
        tmp_dir / ".dvcignore",
        tmp_dir / ".gitignore",
        tmp_dir / "lorem",
        tmp_dir / "lorem.dvc",
        tmp_dir / "dir",
        tmp_dir / "dir" / "repo.txt",
    ]

    actual = []
    for root, dirs, files in tree.walk(tmp_dir, dvcfiles=True):
        for entry in dirs + files:
            actual.append(os.path.normpath(os.path.join(root, entry)))

    expected = [str(path) for path in expected]
    assert set(actual) == set(expected)
    assert len(actual) == len(expected)

    assert tree.isfile(tmp_dir / "lorem") is True
    assert tree.isfile(tmp_dir / "dir" / "repo" / "foo") is False
    assert tree.isdir(tmp_dir / "dir" / "repo") is False
    assert tree.isdir(tmp_dir / "dir") is True

    assert tree.isdvc(tmp_dir / "lorem") is True
    assert tree.isdvc(tmp_dir / "dir" / "repo" / "dir1") is False

    assert tree.exists(tmp_dir / "dir" / "repo.txt") is True
    assert tree.exists(tmp_dir / "repo" / "ipsum") is False


def test_get_hash_cached_file(tmp_dir, dvc, mocker):
    tmp_dir.dvc_gen({"foo": "foo"})
    tree = RepoTree(dvc)
    dvc_tree_spy = mocker.spy(tree._dvctrees[dvc.root_dir], "get_file_hash")
    assert tree.get_hash(PathInfo(tmp_dir) / "foo") == HashInfo(
        "md5", "acbd18db4cc2f85cedef654fccc4a4d8",
    )
    assert dvc_tree_spy.called


def test_get_hash_cached_dir(tmp_dir, dvc, mocker):
    tmp_dir.dvc_gen(
        {"dir": {"foo": "foo", "bar": "bar", "subdir": {"data": "data"}}}
    )
    tree = RepoTree(dvc)
    get_file_hash_spy = mocker.spy(tree, "get_file_hash")
    dvc_tree_spy = mocker.spy(tree._dvctrees[dvc.root_dir], "get_dir_hash")
    assert tree.get_hash(PathInfo(tmp_dir) / "dir") == HashInfo(
        "md5", "8761c4e9acad696bee718615e23e22db.dir",
    )
    assert get_file_hash_spy.called
    assert not dvc_tree_spy.called
    get_file_hash_spy.reset_mock()

    shutil.rmtree(tmp_dir / "dir")
    assert tree.get_hash(PathInfo(tmp_dir) / "dir") == HashInfo(
        "md5", "8761c4e9acad696bee718615e23e22db.dir",
    )
    assert not get_file_hash_spy.called
    assert dvc_tree_spy.called


def test_get_hash_cached_granular(tmp_dir, dvc, mocker):
    tmp_dir.dvc_gen(
        {"dir": {"foo": "foo", "bar": "bar", "subdir": {"data": "data"}}}
    )
    tree = RepoTree(dvc, fetch=True)
    dvc_tree_spy = mocker.spy(tree._dvctrees[dvc.root_dir], "get_file_hash")
    subdir = PathInfo(tmp_dir) / "dir" / "subdir"
    assert tree.get_hash(subdir) == HashInfo(
        "md5", "af314506f1622d107e0ed3f14ec1a3b5.dir",
    )
    assert tree.get_hash(subdir / "data") == HashInfo(
        "md5", "8d777f385d3dfec8815d20f7496026dc",
    )
    assert dvc_tree_spy.called


def test_get_hash_mixed_dir(tmp_dir, scm, dvc):
    tmp_dir.gen({"dir": {"foo": "foo", "bar": "bar"}})
    tmp_dir.dvc.add(os.path.join("dir", "foo"))
    tmp_dir.scm.add(
        [
            os.path.join("dir", "bar"),
            os.path.join("dir", ".gitignore"),
            os.path.join("dir", "foo.dvc"),
        ]
    )
    tmp_dir.scm.commit("add dir")

    tree = RepoTree(dvc)
    actual = tree.get_hash(PathInfo(tmp_dir) / "dir")
    expected = HashInfo("md5", "e1d9e8eae5374860ae025ec84cfd85c7.dir")
    assert actual == expected


def test_get_hash_dirty_file(tmp_dir, dvc):
    tmp_dir.dvc_gen("file", "file")
    (tmp_dir / "file").write_text("something")

    tree = RepoTree(dvc)
    actual = tree.get_hash(PathInfo(tmp_dir) / "file")
    expected = HashInfo("md5", "8c7dd922ad47494fc02c388e12c00eac")
    assert actual == expected


def test_get_hash_dirty_dir(tmp_dir, dvc):
    tmp_dir.dvc_gen({"dir": {"foo": "foo", "bar": "bar"}})
    (tmp_dir / "dir" / "baz").write_text("baz")

    tree = RepoTree(dvc)
    actual = tree.get_hash(PathInfo(tmp_dir) / "dir")
    expected = HashInfo("md5", "ba75a2162ca9c29acecb7957105a0bc2.dir")
    assert actual == expected
    assert len(actual.dir_info) == 3


@pytest.mark.parametrize("traverse_subrepos", [True, False])
def test_walk_nested_subrepos(tmp_dir, dvc, scm, traverse_subrepos):
    # generate a dvc and fs structure, with suffix based on repo's basename
    def fs_structure(suffix):
        return {
            f"foo-{suffix}": f"foo-{suffix}",
            f"dir-{suffix}": {f"bar-{suffix}": f"bar-{suffix}"},
        }

    def dvc_structure(suffix):
        return {
            f"lorem-{suffix}": f"lorem-{suffix}",
            f"dvc-{suffix}": {f"ipsum-{suffix}": f"ipsum-{suffix}"},
        }

    paths = ["subrepo1", "subrepo2", "subrepo1/subrepo3"]
    subrepos = [tmp_dir / path for path in paths]
    for repo_dir in subrepos:
        make_subrepo(repo_dir, scm)

    extras = {".dvcignore", ".gitignore"}  # these files are always there
    expected = {}
    for repo_dir in subrepos + [tmp_dir]:
        base = os.path.basename(repo_dir)
        scm_files = fs_structure(base)
        dvc_files = dvc_structure(base)
        with repo_dir.chdir():
            repo_dir.scm_gen(scm_files, commit=f"git add in {repo_dir}")
            repo_dir.dvc_gen(dvc_files, commit=f"dvc add in {repo_dir}")

        if traverse_subrepos or repo_dir == tmp_dir:
            expected[str(repo_dir)] = set(
                scm_files.keys() | dvc_files.keys() | extras
            )
            # files inside a dvc directory
            expected[str(repo_dir / f"dvc-{base}")] = {f"ipsum-{base}"}
            # files inside a git directory
            expected[str(repo_dir / f"dir-{base}")] = {f"bar-{base}"}

    if traverse_subrepos:
        # update subrepos
        expected[str(tmp_dir)].update(["subrepo1", "subrepo2"])
        expected[str(tmp_dir / "subrepo1")].add("subrepo3")

    actual = {}
    tree = RepoTree(dvc, subrepos=traverse_subrepos)
    for root, dirs, files in tree.walk(str(tmp_dir)):
        actual[root] = set(dirs + files)
    assert expected == actual
