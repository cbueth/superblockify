"""Tests for the distance calculations."""

import pytest
from matplotlib import pyplot as plt
from numpy import inf

from superblockify.metrics.distances import (
    calculate_path_distance_matrix,
    calculate_euclidean_distance_matrix_projected,
    calculate_partitioning_distance_matrix,
)


@pytest.mark.parametrize("weight", ["length", "travel_time", None])
def test_calculate_distance_matrix(test_city_small_copy, weight):
    """Test calculating all pairwise distances for the full graphs."""
    _, graph = test_city_small_copy
    calculate_path_distance_matrix(graph, weight=weight, plot_distributions=True)
    # With node ordering
    calculate_path_distance_matrix(
        graph, node_order=list(graph.nodes), plot_distributions=True
    )
    plt.close("all")


def test_calculate_distance_matrix_negative_weight(test_city_small_copy):
    """Test calculating all pairwise distances for the full graphs with negative
    weights.
    """
    _, graph = test_city_small_copy
    # Change the first edge length to -1
    graph.edges[list(graph.edges)[0]]["length"] = -1
    with pytest.raises(ValueError):
        calculate_path_distance_matrix(graph, weight="length")


def test_calculate_euclidean_distance_matrix_projected(test_city_all_copy):
    """Test calculating all pairwise Euclidean distances for the full graphs.
    Projected."""
    _, graph = test_city_all_copy
    calculate_euclidean_distance_matrix_projected(graph, plot_distributions=True)
    # With node ordering
    calculate_euclidean_distance_matrix_projected(
        graph, node_order=list(graph.nodes), plot_distributions=True
    )
    plt.close("all")


@pytest.mark.parametrize(
    "key,value",
    [
        ("x", None),
        ("y", None),
        ("x", "a"),
        ("y", "a"),
        ("x", inf),
        ("y", inf),
        ("x", -inf),
        ("y", -inf),
    ],
)
def test_calculate_euclidean_distance_matrix_projected_faulty_coords(
    test_city_small_copy, key, value
):
    """Test calculating all pairwise Euclidean distances for the full graphs
    with missing coordinates. Projected.
    """
    _, graph = test_city_small_copy
    # Change key attribute of first node
    graph.nodes[list(graph.nodes)[0]][key] = value
    with pytest.raises(ValueError):
        calculate_euclidean_distance_matrix_projected(graph)


def test_calculate_euclidean_distance_matrix_projected_unprojected_graph(
    test_city_small_copy,
):
    """Test `calculate_euclidean_distance_matrix_projected` exception handling
    unprojected graph."""
    _, graph = test_city_small_copy

    # Pseudo-unproject graph
    graph.graph["crs"] = "epsg:4326"
    with pytest.raises(ValueError):
        calculate_euclidean_distance_matrix_projected(graph)

    # Delete crs attribute
    graph.graph.pop("crs")
    with pytest.raises(ValueError):
        calculate_euclidean_distance_matrix_projected(graph)


@pytest.mark.parametrize("predefined_node_order", [True, False])
@pytest.mark.parametrize("max_mem_factor", [0.5, 0.0])
def test_calculate_partitioning_distance_matrix(
    test_city_small_precalculated_copy, predefined_node_order, max_mem_factor
):
    """Test calculating distances for partitioned graph by design."""
    part = test_city_small_precalculated_copy
    if predefined_node_order:
        dist, pred = calculate_partitioning_distance_matrix(
            part,
            # reverse node order
            node_order=list(part.graph.nodes)[::-1],
            plot_distributions=True,
            check_overlap=True,
            max_mem_factor=max_mem_factor,
        )
    else:
        dist, pred = calculate_partitioning_distance_matrix(
            part,
            plot_distributions=True,
            check_overlap=True,
            max_mem_factor=max_mem_factor,
        )
    plt.close("all")
    assert dist.shape == (part.graph.number_of_nodes(),) * 2
    assert dist.dtype.kind == "f"
    assert pred.shape == (part.graph.number_of_nodes(),) * 2
    assert pred.dtype.kind == "i"


def test_calculate_partitioning_distance_matrix_duplicate_partition_names(
    test_city_small_precalculated_copy,
):
    """Test calculating distances for partitioned graph with duplicate partition
    names."""
    part = test_city_small_precalculated_copy
    # Duplicate partitions /component
    if part.components is not None:
        part.components += part.components
    else:
        part.partitions += part.partitions

    with pytest.raises(ValueError):
        calculate_partitioning_distance_matrix(part)


def test_calculate_partitioning_distance_matrix_partitions_overlap(
    test_city_small_precalculated_copy,
):
    """Test calculating distances for partitioned graph with overlapping
    partitions."""
    part = test_city_small_precalculated_copy
    # Duplicate partitions /component
    if part.components is not None:
        # Duplicate component but with different name
        part.components += [part.components[-1].copy()]
        # Rename duplicate partition
        part.components[-1]["name"] = part.components[-1]["name"] + "_dup"
    else:
        part.partitions += [part.partitions[1].copy()]
        part.partitions[-1]["name"] = part.partitions[-1]["name"] + "_dup"

    with pytest.raises(ValueError):
        calculate_partitioning_distance_matrix(part, check_overlap=True)
