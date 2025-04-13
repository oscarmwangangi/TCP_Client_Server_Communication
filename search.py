import bisect
import time


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

        if not reread_on_query:
            self.load_file()
            if self.method == "binary":
                self.sorted_data = sorted(self.data)

    def load_file(self):
        """Load file into self.data, stripping newlines but keeping content."""
        with open(self.path, "r", encoding="utf-8") as file:
            self.data = [
                line.rstrip("\n")
                for line in file
                if line.rstrip("\n")
            ]

    def linear_search(self, query: str) -> bool:
        """Perform linear search for query in loaded data."""
        query = query.rstrip("\n")
        return any(
            line.strip() == query
            for line in self.data
        )

    def binary_search(self, query: str) -> bool:
        """Perform binary search for query in sorted data."""
        query = query.strip()
        index = bisect.bisect_left(self.sorted_data, query)
        return (
            index != len(self.sorted_data)
            and self.sorted_data[index] == query)

    def search(self, query: str) -> bool:
        """Search for query using specified method."""
        query = query.rstrip("\n")
        if not query:
            return False

        start = time.time()

        if self.reread_on_query:
            with open(self.path, "r", encoding="utf-8") as file:
                current_data = [
                    line.rstrip("\n")
                    for line in file
                    if line.rstrip("\n")
                ]
                if self.method == "binary":
                    current_data_sorted = sorted(
                        line.strip()
                        for line in current_data
                    )
                    query_stripped = query.strip()
                    index = bisect.bisect_left(
                        current_data_sorted,
                        query_stripped
                    )
                    result = (
                        index != len(current_data_sorted)
                        and current_data_sorted[index] == query_stripped
                    )
                else:
                    result = any(
                        line.strip() == query.strip()
                        for line in current_data
                    )
        else:
            if self.method == "binary":
                result = self.binary_search(query)
            else:
                result = self.linear_search(query)

        end = time.time()
        print(f"Search time: {end - start:.6f}s")
        return result
