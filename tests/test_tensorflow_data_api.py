"""Tests for TileDB integration with Tensorflow Data API."""

import os

import numpy as np
import pytest
import tensorflow as tf

import tiledb
from tiledb.ml.readers._batch_utils import tensor_generator
from tiledb.ml.readers.tensorflow import (
    TensorflowDenseBatch,
    TensorflowSparseBatch,
    TensorflowTileDBDataset,
)

from .utils import create_rand_labels, ingest_in_tiledb, validate_tensor_generator

# Suppress all Tensorflow messages
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)

# Test parameters
NUM_OF_CLASSES = 5
BATCH_SIZE = 32
ROWS = 1000


@pytest.mark.parametrize("input_shape", [(10,), (10, 3)])
@pytest.mark.parametrize("num_attrs", [1, 2])
@pytest.mark.parametrize("batch_shuffle", [True, False])
@pytest.mark.parametrize("within_batch_shuffle", [True, False])
@pytest.mark.parametrize("buffer_size", [50, None])
class TestTensorflowTileDBDatasetDense:
    @pytest.mark.parametrize("sparse_y", [True, False])
    def test_dense_x(
        self,
        tmpdir,
        input_shape,
        num_attrs,
        batch_shuffle,
        within_batch_shuffle,
        buffer_size,
        sparse_y,
    ):
        if sparse_y and within_batch_shuffle:
            pytest.skip("Sparse y not supported with within_batch_shuffle")

        uri_x, uri_y = ingest_in_tiledb(
            tmpdir,
            data_x=np.random.rand(ROWS, *input_shape),
            data_y=create_rand_labels(ROWS, NUM_OF_CLASSES, one_hot=sparse_y),
            sparse_x=False,
            sparse_y=sparse_y,
            batch_size=BATCH_SIZE,
            num_attrs=num_attrs,
        )
        attrs = [f"features_{attr}" for attr in range(num_attrs)]
        with tiledb.open(uri_x) as x, tiledb.open(uri_y) as y:
            for pass_attrs in True, False:
                kwargs = dict(
                    x_array=x,
                    y_array=y,
                    batch_size=BATCH_SIZE,
                    buffer_size=buffer_size,
                    batch_shuffle=batch_shuffle,
                    within_batch_shuffle=within_batch_shuffle,
                    x_attrs=attrs if pass_attrs else [],
                    y_attrs=attrs if pass_attrs else [],
                )

                # Test buffer_size < batch_size
                dataset = TensorflowTileDBDataset(
                    **dict(kwargs, buffer_size=BATCH_SIZE - 1)
                )
                with pytest.raises(Exception) as excinfo:
                    next(iter(dataset))
                assert "Buffer size should be greater or equal to batch size" in str(
                    excinfo.value
                )

                # Test generator
                dataset = TensorflowTileDBDataset(**kwargs)
                assert isinstance(dataset, tf.data.Dataset)
                # Test the generator twice: once with the public api (TensorflowTileDBDataset)
                # and once with calling tensor_generator directly. Although the former calls
                # the latter internally, it is not reported as covered by the coverage report
                # due to https://github.com/tensorflow/tensorflow/issues/33759
                generators = [
                    dataset,
                    tensor_generator(
                        dense_batch_cls=TensorflowDenseBatch,
                        sparse_batch_cls=TensorflowSparseBatch,
                        **kwargs,
                    ),
                ]
                for generator in generators:
                    validate_tensor_generator(
                        generator,
                        num_attrs,
                        BATCH_SIZE,
                        shape_x=input_shape,
                        shape_y=(NUM_OF_CLASSES,) if sparse_y else (),
                        sparse_x=False,
                        sparse_y=sparse_y,
                    )

    def test_unequal_num_rows(
        self,
        tmpdir,
        input_shape,
        num_attrs,
        batch_shuffle,
        within_batch_shuffle,
        buffer_size,
    ):
        uri_x, uri_y = ingest_in_tiledb(
            tmpdir,
            # Add one extra row on X
            data_x=np.random.rand(ROWS + 1, *input_shape),
            data_y=create_rand_labels(ROWS, NUM_OF_CLASSES),
            sparse_x=False,
            sparse_y=False,
            batch_size=BATCH_SIZE,
            num_attrs=num_attrs,
        )
        attrs = [f"features_{attr}" for attr in range(num_attrs)]
        with tiledb.open(uri_x) as x, tiledb.open(uri_y) as y:
            for pass_attrs in True, False:
                with pytest.raises(ValueError):
                    TensorflowTileDBDataset(
                        x_array=x,
                        y_array=y,
                        batch_size=BATCH_SIZE,
                        buffer_size=buffer_size,
                        batch_shuffle=batch_shuffle,
                        within_batch_shuffle=within_batch_shuffle,
                        x_attrs=attrs if pass_attrs else [],
                        y_attrs=attrs if pass_attrs else [],
                    )
