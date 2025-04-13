import os
import sys
from unittest.mock import mock_open, patch

import pytest

# Add project directory to sys.path for local imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from search import Searcher  # noqa: E402


# Test Data
TEST_FILE_CONTENT = """1;2;3
7;0;6;28;0;23;5;0;
10;0;1;26;0;8;3;0;
"""

WHITESPACE_FILE_CONTENT = "  hello  \nworld  \n"
SORTED_FILE_CONTENT = "a\nb\nc\nd\n"
SINGLE_LINE_CONTENT = "single_line_content"
EMPTY_LINES_CONTENT = "line1\n\nline2\n  \nline3"


@pytest.fixture
def sample_data_file(tmp_path):
    """Creates a temporary test file with sample data"""
    test_file = tmp_path / "test_data.txt"
    test_file.write_text(TEST_FILE_CONTENT)
    return str(test_file)


# Modify existing tests to use the fixture
def test_search_with_real_file(sample_data_file):
    """Test with actual file operations using pytest tmpdir"""
    searcher = Searcher(sample_data_file)
    assert searcher.search("7;0;6;28;0;23;5;0;") is True
    assert searcher.search("nonexistent") is False


# Update other tests to consistently use mocks
def test_file_not_found_error():
    with patch("builtins.open",
               side_effect=FileNotFoundError("File not found")):
        with pytest.raises(FileNotFoundError):
            Searcher("nonexistent_file.txt")


# Algorithm Tests
@pytest.mark.parametrize("algorithm", ["linear", "binary"])
def test_search_algorithms(algorithm):
    with patch("builtins.open", mock_open(read_data=TEST_FILE_CONTENT)):
        searcher = Searcher("dummy.txt", algorithm=algorithm)
        assert searcher.search("7;0;6;28;0;23;5;0;") is True
        assert searcher.search("nonexistent") is False


# Edge Cases
def test_empty_file_search():
    with patch("builtins.open", mock_open(read_data="")):
        searcher = Searcher("empty.txt")
        assert searcher.search("anything") is False


def test_partial_match_not_found():
    with patch("builtins.open", mock_open(read_data=TEST_FILE_CONTENT)):
        searcher = Searcher("dummy.txt")
        assert searcher.search("7;0;6") is False  # Partial match fails


def test_binary_search_edge_cases():
    with patch("builtins.open", mock_open(read_data=SORTED_FILE_CONTENT)):
        searcher = Searcher("sorted.txt", algorithm="binary")
        assert searcher.search("a") is True  # first element
        assert searcher.search("d") is True  # last element
        assert searcher.search("b") is True  # middle element
        assert searcher.search("e") is False  # beyond end


def test_whitespace_handling():
    with patch("builtins.open", mock_open(read_data=WHITESPACE_FILE_CONTENT)):
        searcher = Searcher("whitespace.txt")
        assert searcher.search("hello") is True
        assert searcher.search("  hello  ") is False  # exact match required


def test_single_line_file():
    with patch("builtins.open", mock_open(read_data=SINGLE_LINE_CONTENT)):
        searcher = Searcher("single.txt")
        assert searcher.search("single_line_content") is True
        assert searcher.search("other") is False


def test_empty_lines_in_file():
    with patch("builtins.open", mock_open(read_data=EMPTY_LINES_CONTENT)):
        searcher = Searcher("empty_lines.txt")
        assert searcher.search("line1") is True
        assert searcher.search("") is False  # empty line shouldn't match
        assert searcher.search("line2") is True


# File Handling
def test_file_not_found_handling():
    with pytest.raises(FileNotFoundError):
        Searcher("nonexistent_file.txt")


def test_file_permission_error():
    with patch("builtins.open", side_effect=PermissionError):
        with pytest.raises(PermissionError):
            Searcher("restricted.txt")


# Parameter and Configuration Tests
def test_reread_on_query():
    with patch("builtins.open", mock_open(read_data=TEST_FILE_CONTENT)):
        searcher = Searcher("dummy.txt", reread_on_query=True)
        assert searcher.search("1;2;3") is True
        # Verify it rereads by changing mock data
        with patch("builtins.open", mock_open(read_data="new_content")):
            assert searcher.search("new_content") is True


def test_algorithm_parameter_precedence():
    with patch("builtins.open", mock_open(read_data=TEST_FILE_CONTENT)):
        searcher = Searcher("dummy.txt", method="linear", algorithm="binary")
        assert searcher.method == "binary"  # algorithm should take precedence


# Performance Tests (basic verification)
def test_search_timing_output(capsys):
    with patch("builtins.open", mock_open(read_data=TEST_FILE_CONTENT)):
        searcher = Searcher("dummy.txt")
        searcher.search("1;2;3")
        captured = capsys.readouterr()
        assert "Search time:" in captured.out


def test_unicode_handling():
    """Test search with Unicode characters"""
    unicode_content = "你好世界\nこんにちは世界\n안녕세계\n"
    with patch("builtins.open", mock_open(read_data=unicode_content)):
        searcher = Searcher("unicode.txt")
        assert searcher.search("你好世界") is True
        assert searcher.search("안녕세계") is True


def test_long_line_handling():
    """Test with very long lines (>1MB)"""
    long_content = "a" * 10_000_000 + "\nshort\n"
    with patch("builtins.open", mock_open(read_data=long_content)):
        searcher = Searcher("long_lines.txt")
        assert searcher.search("short") is True
        assert searcher.search("a" * 10) is False  # Shouldn't match partial


def test_malformed_file_handling():
    """Test with non-UTF8 files"""
    with patch("builtins.open") as mock_open:
        mock_open.return_value.__enter__.return_value.read.side_effect = (
            UnicodeDecodeError(
                'utf-8', b'\xff\xfe\xfd', 0, 1, 'Invalid start byte'
            )
        )
        searcher = Searcher("binary.data")
        assert searcher.search("anything") is False
