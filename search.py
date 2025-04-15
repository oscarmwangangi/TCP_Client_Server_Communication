import bisect
import time
import mmap


class Searcher:
    def __init__(
        self,
        path: str,
        method: str = "linear",
        reread_on_query: bool = False,
        algorithm: str = None,
    ):
        self.path = path
        self.method = algorithm if algorithm else method
        self.reread_on_query = reread_on_query
        self.data = []
        self.sorted_data = []
        self._mmap = None
        self._file_handle = None

        # Memory mapping initialization
        if not reread_on_query:
            self._initialize_memory_mapping()
            self.load_file()

    def _initialize_memory_mapping(self):
        """Initialize memory mapping for efficient file access."""
        try:
            self._file_handle = open(self.path, 'rb')
            self._mmap = mmap.mmap(
                self._file_handle.fileno(), 0, access=mmap.ACCESS_READ)
        except Exception as e:
            # Fall back to regular file operations if mmap fails
            print(
                f"Memory mapping failed,"
                f"falling back to regular file operations: {
                    str(e)}")
            self._mmap = None
            self._file_handle = None

    def load_file(self):
        """Load file into self.data using optimized methods."""
        if self._mmap:
            pos = 0
            while pos < len(self._mmap):
                # Directly call find on the mmap object
                nl_pos = self._mmap.find(b'\n', pos)
                if nl_pos == -1:
                    nl_pos = len(self._mmap)
                # Decode the bytes and strip all whitespace (not just newlines)
                line = self._mmap[pos:nl_pos].decode('utf-8').strip()
                if line:  # Only add non-empty lines
                    self.data.append(line)
                pos = nl_pos + 1
        else:
            # Fallback to regular file operations with full stripping of
            # whitespace
            with open(self.path, "r", encoding="utf-8") as file:
                self.data = [line.strip() for line in file if line.strip()]

        if self.method == "binary":
            self.sorted_data = sorted(self.data)

            if self.method == "binary":
                self.sorted_data = sorted(self.data)

    def linear_search(self, query: str) -> bool:
        """Optimized linear search with early termination."""
        query = query.rstrip("\n")
        return any(line == query for line in self.data)

    def binary_search(self, query: str) -> bool:
        """Optimized binary search with proper string handling."""
        query = query.strip()
        index = bisect.bisect_left(self.sorted_data, query)
        return index != len(
            self.sorted_data) and self.sorted_data[index] == query

    def _search_with_reread(self, query: str) -> bool:
        """Optimized file re-reading search."""
        query = query.rstrip("\n")
        if not query:
            return False

        if self._mmap:
            # Use memory mapping for re-reads
            view = memoryview(self._mmap)
            pos = 0
            while pos < len(view):
                nl_pos = view.find(b'\n', pos)
                if nl_pos == -1:
                    nl_pos = len(view)
                line = view[pos:nl_pos].tobytes().decode('utf-8').rstrip('\n')
                if line == query:
                    return True
                pos = nl_pos + 1
            return False
        else:
            # Fallback to regular file reading
            with open(self.path, "r", encoding="utf-8") as file:
                if self.method == "binary":
                    current_data = sorted(line.rstrip("\n")
                                          for line in file
                                          if line.rstrip("\n"))
                    query = query.strip()
                    index = bisect.bisect_left(current_data, query)
                    return index != len(
                        current_data) and current_data[index] == query
                else:
                    return any(line.rstrip("\n") == query for line in file)

    def search(self, query: str) -> bool:
        """Search for query using specified method with timing."""
        query = query.rstrip("\n")
        if not query:
            return False

        start = time.perf_counter()

        if self.reread_on_query:
            result = self._search_with_reread(query)
        else:
            if self.method == "binary":
                result = self.binary_search(query)
            else:
                result = self.linear_search(query)

        end = time.perf_counter()
        print(f"Search time: {(end - start) * 1000:.3f}ms")
        return result

    def __del__(self):
        """Clean up resources."""
        if self._mmap:
            self._mmap.close()
        if self._file_handle:
            self._file_handle.close()
