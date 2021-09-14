"""Functionality for loading data directly from dense TileDB arrays into the PyTorch Dataloader API."""
import tiledb
import torch
import math
from typing import List, Optional


class PyTorchTileDBDenseDataset(torch.utils.data.IterableDataset):
    """
    Class that implements all functionality needed to load data from TileDB directly to the
    PyTorch Dataloader API.
    """

    def __init__(
        self,
        x_array: tiledb.Array,
        y_array: tiledb.Array,
        batch_size: int,
        x_attribute_names: Optional[List[str]] = [],
        y_attribute_names: Optional[List[str]] = [],
    ):
        """
        Initialises a PyTorchTileDBDenseDataset that inherits from PyTorch IterableDataset.
        :param x_array: TileDB Dense Array. Array that contains features.
        :param y_array: TileDB Dense Array. Array that contains labels.
        :param batch_size: Integer. The size of the batch that the generator will return. Remember to set batch_size=None
        when calling the PyTorch Dataloader API, because batching is taking place inside the TileDB IterableDataset.
        :param x_attribute_names: List of str. A list that contains the attribute names of TileDB array x.
        :param y_attribute_names: List of str. A list that contains the attribute names of TileDB array y.
        For optimal reads from a TileDB array, it is recommended to set the batch size equal to the tile extent of the
        dimension we query (here, we always query the first dimension of a TileDB array) in order to get a slice (batch)
        of the data. For example, in case the tile extent of the first dimension of a TileDB array (x or y) is equal to
        32, it's recommended to set batch_size=32. Any batch size will work, but in case it's not equal the tile extent
        of the first dimension of the TileDB array, you won't achieve highest read speed. For more details on tiles,
        tile extent and indices in TileDB, please check here:
        https://docs.tiledb.com/main/solutions/tiledb-embedded/performance-tips/choosing-tiling-and-cell-layout#dense-arrays
        """

        # Check that x and y have the same number of rows
        if x_array.schema.domain.shape[0] != y_array.schema.domain.shape[0]:
            raise ValueError(
                "X and Y should have the same number of rows, i.e., the 1st dimension "
                "of TileDB arrays X, Y should be of equal domain extent."
            )

        self.x = x_array
        self.y = y_array
        self.batch_size = batch_size

        # If a user doesn't pass explicit attribute names to return per batch, we return all attributes.
        self.x_attribute_names = (
            [x_array.schema.attr(idx).name for idx in range(x_array.schema.nattr)]
            if not x_attribute_names
            else x_attribute_names
        )

        self.y_attribute_names = (
            [y_array.schema.attr(idx).name for idx in range(y_array.schema.nattr)]
            if not y_attribute_names
            else y_attribute_names
        )

    def __iter__(self):
        worker_info = torch.utils.data.get_worker_info()

        # Get number of observations
        rows = self.x.schema.domain.shape[0]

        # Single worker - return full iterator
        if worker_info is None:
            iter_start = 0
            iter_end = rows

        # Multiple workers - split workload
        else:
            per_worker = int(math.ceil(rows / worker_info.num_workers))
            worker_id = worker_info.id
            iter_start = worker_id * per_worker
            iter_end = min(iter_start + per_worker, rows)

        # Loop over batches
        for offset in range(iter_start, iter_end, self.batch_size):
            x_batch = self.x[offset : offset + self.batch_size]
            y_batch = self.y[offset : offset + self.batch_size]
            # Yield the next training batch
            yield tuple(x_batch[attr] for attr in self.x_attribute_names) + tuple(
                y_batch[attr] for attr in self.y_attribute_names
            )

    def __len__(self):
        return self.x.shape[0]
