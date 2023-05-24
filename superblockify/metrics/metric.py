"""Metric object for the superblockify package."""
import pickle
from os.path import join, exists

from .distances import (
    calculate_partitioning_distance_matrix,
    calculate_path_distance_matrix,
    calculate_euclidean_distance_matrix_projected,
)
from .measures import (
    calculate_global_efficiency,
    calculate_directness,
    write_relative_increase_to_edges,
    calculate_coverage,
    betweenness_centrality,
    calculate_high_bc_clustering,
)
from .plot import (
    plot_distance_matrices,
    plot_distance_matrices_pairwise_relative_difference,
    plot_component_wise_travel_increase,
    plot_relative_difference,
    plot_relative_increase_on_graph,
)
from ..config import logger, RESULTS_DIR, CLUSTERING_PERCENTILE
from ..plot import save_plot
from ..utils import compare_dicts


class Metric:
    """Metric object to be used with partitioners.

    A metric object is used to calculate the quality of a partitioning.
    It holds the information on several network metrics, which can be read,
    and can be used to calculate them when passing a Partitioner object.

    There are different network measures
    - d_E(i, j): Euclidean
    - d_S(i, j): Shortest path on full graph
    - d_N(i, j): Shortest path with ban through LTNs

    We define several types of combinations of these metrics:
    (i, j are nodes in the graph)

    The network metrics are the following:

    - Coverage (fraction of network covered by a partition):
      C = sum(1 if i in partition else 0) / len(graph.nodes)

    - Components (number of connected components):
      C = len(graph.components)

    - Average path length:
        - A(E) = mean(d_E(i, j)) where i <> j
        - A(S) = mean(d_S(i, j)) where i <> j
        - A(N) = mean(d_N(i, j)) where i <> j

    - Directness:
        - D(E, S) = mean(d_E(i, j) / d_S(i, j)) where i <> j
        - D(E, N) = mean(d_E(i, j) / d_N(i, j)) where i <> j
        - D(S, N) = mean(d_S(i, j) / d_N(i, j)) where i <> j

    - Global efficiency:
        - G(i; S/E) = sum(1/d_S(i, j)) / sum(1/d_E(i, j)) where for each sum i <> j
        - G(i; N/E) = sum(1/d_N(i, j)) / sum(1/d_E(i, j)) where for each sum i <> j
        - G(i; N/S) = sum(1/d_N(i, j)) / sum(1/d_S(i, j)) where for each sum i <> j

    Attributes
    ----------
    coverage : float
        The coverage of the partitioning takes of the whole graph
    num_components : int
        The number of components in the graph
    avg_path_length : dict
        The average path length of the graph for each network measure
        {"E": float, "S": float, "N": float}
    directness : dict
        The directness of the graph for the network measure ratios
        {"ES": float, "EN": float, "SN": float}
    global_efficiency : dict
        The global efficiency of the graph for each network measure
        {"SE": float, "NE": float, "NS": float}
    local_efficiency : dict
        The local efficiency of the graph for each network measure
        {"SE": float, "NE": float, "NS": float}
    high_bc_clustering : float
        The clustering coefficient of the nodes with the highest betweenness centrality
    high_bc_anisotropy : float
        The anisotropy of the nodes with the highest betweenness centrality

    distance_matrix : dict
        The distance matrices for each network measure
    predecessor_matrix : dict
        The predecessor matrices for each network measure
    unit : str
        The unit to use for the shortest distance calculation, either "time",
        "distance", ``None`` for hops, or a custom unit string found as edge attribute
        in the graph
    node_list : list
        The list of nodes in the graph, used for the distance matrices
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, unit="time"):
        """Construct a metric object.

        Parameters
        ----------
        unit : str, optional
            The unit to use for the shortest distance calculation, by default "time",
            can also be "distance", if ``None`` count hops.
        """

        # Partitioning metrics
        self.coverage = None
        self.num_components = None
        self.avg_path_length = {"S": None, "N": None}
        self.directness = {"SN": None}
        self.global_efficiency = {"NS": None}
        self.high_bc_clustering = None
        self.high_bc_anisotropy = None

        # Intermediate results
        self.distance_matrix = {}
        self.predecessor_matrix = {}
        self.unit = unit
        self.node_list = None

    def unit_symbol(self):
        """Return unit string represented by the :attr:`unit` attribute.

        Returns
        -------
        str
            The unit symbol, either "s", "m", "hops" or the unit string in brackets.
        """
        if self.unit == "time":
            return "s"
        if self.unit == "distance":
            return "m"
        if self.unit is None:
            return "hops"
        return f"({self.unit})"

    def calculate_before(self, partitioner, make_plots=False):
        """Calculate metrics on unrestricted graph

        Metrics that should be available to partitioners for use in their
        partitioning algorithm. This includes

        - Shortest paths and distances on the unrestricted graph
        - Betweenness centralities on the unrestricted graph

        Parameters
        ----------
        partitioner : BasePartitioner
            The partitioner object to calculate the metrics for
        """
        if self.node_list is None and partitioner.partitions is None:
            self.node_list = list(partitioner.graph.nodes)
        else:
            self.node_list = partitioner.get_sorted_node_list()

        if self.unit == "distance":
            self.distance_matrix["E"] = calculate_euclidean_distance_matrix_projected(
                partitioner.graph,
                node_order=self.node_list,
                plot_distributions=make_plots,
            )
        # On the full graph (S)
        weight = (
            "length"
            if self.unit == "distance"
            else "travel_time"
            if self.unit == "time"
            else self.unit
        )
        (
            self.distance_matrix["S"],
            self.predecessor_matrix["S"],
        ) = calculate_path_distance_matrix(
            partitioner.graph,
            weight=weight,
            unit_symbol=self.unit_symbol(),
            node_order=self.node_list,
            plot_distributions=make_plots,
        )
        betweenness_centrality(
            partitioner.graph,
            self.node_list,
            self.distance_matrix["S"],
            self.predecessor_matrix["S"],
            weight=weight,
            #  No `attr_suffix` for the full graph
        )

        self.calculate_high_bc_clustering(partitioner.graph, CLUSTERING_PERCENTILE)

    def calculate_all(
        self,
        partitioner,
        replace_max_speeds=True,
        num_workers=None,
        chunk_size=1,
        make_plots=False,
    ):
        """Calculate all metrics for the partitioning.

        If :meth:`calculate_before` has been called before partitioning, only the
        remaining metrics are calculated.

        Parameters
        ----------
        partitioner : BasePartitioner
            The partitioner object to calculate the metrics for
        replace_max_speeds : bool, optional
            If True and unit is "time", calculate the quickest paths in the restricted
            graph with the max speeds :attr:`V_MAX_LTN` and :attr:`V_MAX_SPARSE` set in
            :mod:`superblockify.config`. Default is True.
        num_workers : int, optional
            The number of workers to use for multiprocessing. If None, use
            min(32, os.cpu_count() + 4), by default None
        chunk_size : int, optional
            The chunk size to use for multiprocessing, by default 1
        make_plots : bool, optional
            Whether to make plots of the distributions of the distances for each
            network measure, by default False
        """
        # pylint: disable=unused-argument

        #  Calculate also in case it has been called before, as graph might have changed
        self.calculate_before(partitioner, make_plots=make_plots)

        if self.unit == "distance":
            self.avg_path_length["E"] = None
            self.directness["ES"], self.directness["EN"] = None, None
            self.global_efficiency["SE"], self.global_efficiency["NE"] = None, None

        self.coverage = calculate_coverage(partitioner, weight="length")
        logger.debug("Coverage (length): %s", self.coverage)

        weight_restricted = (
            "length"
            if self.unit == "distance"
            else "travel_time"
            if self.unit == "time" and not replace_max_speeds
            else "travel_time_restricted"
            if self.unit == "time" and replace_max_speeds
            else self.unit
        )
        (
            self.distance_matrix["N"],
            self.predecessor_matrix["N"],
        ) = calculate_partitioning_distance_matrix(
            partitioner,
            weight=weight_restricted,
            unit_symbol=self.unit_symbol(),
            node_order=self.node_list,
            num_workers=num_workers,
            chunk_size=chunk_size,
            plot_distributions=make_plots,
        )

        betweenness_centrality(
            partitioner.graph,
            self.node_list,
            self.distance_matrix["N"],
            self.predecessor_matrix["N"],
            weight=weight_restricted,
            attr_suffix="_restricted",
        )

        self.calculate_all_measure_sums()

        write_relative_increase_to_edges(
            partitioner.graph, self.distance_matrix, self.node_list, "N", "S"
        )

        if make_plots:
            # sort distance matrix dictionaries to follow start with E, S, N, ...
            d_m = self.distance_matrix
            self.distance_matrix = {}
            for key in ["E", "S", "N"]:
                if key in d_m:
                    self.distance_matrix[key] = d_m[key]
            self.make_all_plots(partitioner)

    def make_all_plots(self, partitioner):
        """Make all plots for the metrics.

        Parameters
        ----------
        partitioner : BasePartitioner
            The partitioner object to calculate the metrics for
        """

        fig, _ = plot_distance_matrices(
            self, name=f"{partitioner.name} - {partitioner.__class__.__name__}"
        )
        save_plot(
            partitioner.results_dir,
            fig,
            f"{partitioner.name}_distance_matrices.pdf",
        )
        fig.show()
        fig, _ = plot_distance_matrices_pairwise_relative_difference(
            self, name=f"{partitioner.name} - {partitioner.__class__.__name__}"
        )
        save_plot(
            partitioner.results_dir,
            fig,
            f"{partitioner.name}_distance_matrices_"
            f"pairwise_relative_difference.pdf",
        )
        fig.show()
        fig, _ = plot_relative_difference(
            self, "N", "S", title=f"{partitioner.name} - {self.__class__.__name__}"
        )
        save_plot(
            partitioner.results_dir,
            fig,
            f"{partitioner.name}_relative_difference_SN.pdf",
        )
        fig.show()
        fig, _ = plot_component_wise_travel_increase(
            partitioner,
            self.distance_matrix,
            self.node_list,
            measure1="N",
            measure2="S",
            unit=self.unit_symbol(),
        )
        save_plot(
            partitioner.results_dir,
            fig,
            f"{partitioner.name}_component_wise_travel_increase.pdf",
        )
        fig, _ = plot_relative_increase_on_graph(partitioner.graph, self.unit_symbol())
        save_plot(
            partitioner.results_dir,
            fig,
            f"{partitioner.name}_relative_increase_on_graph.pdf",
        )

        # self.coverage = self.calculate_coverage(partitioner)
        # logger.debug("Coverage: %s", self.coverage)

    def calculate_all_measure_sums(self):
        """Based on the distance matrix, calculate the network measures.

        Calculate the directness, global and local efficiency for each network measure
        and write them to the corresponding attributes.

        """

        # Directness
        for key in self.directness:
            self.directness[key] = calculate_directness(
                self.distance_matrix, key[0], key[1]
            )
            logger.debug("Directness %s: %s", key, self.directness[key])

        # Global efficiency
        for key in self.global_efficiency:
            self.global_efficiency[key] = calculate_global_efficiency(
                self.distance_matrix, key[0], key[1]
            )
            logger.debug("Global efficiency %s: %s", key, self.global_efficiency[key])

    def calculate_high_bc_clustering(self, graph, percentile):
        """Calculate the high betweenness node clustering and anisotropy.

        High betweenness nodes are the nodes above the given percentile of the
        betweenness centrality distribution.

        Parameters
        ----------
        graph : networkx.Graph
            The graph to calculate the high betweenness node clustering for, needs to
            have x, y, and node_betweenness_normal attribute for each node.
        percentile : float or int
            The percentile of the betweenness centrality to use as a threshold for high
            betweenness nodes. 0.0 < percentile < 100.0.

        Raises
        ------
        ValueError
            If percentile is not a float between 0.0 and 100.0.
        """
        if not isinstance(percentile, (float, int)):
            raise ValueError(
                f"percentile needs to be a float or int, not {type(percentile)}"
            )
        if not 0.0 < percentile < 100.0:
            raise ValueError(
                f"percentile needs to be between 0.0 and 100.0, not {percentile}"
            )

        self.high_bc_clustering, self.high_bc_anisotropy = calculate_high_bc_clustering(
            node_x=[graph.nodes[node]["x"] for node in self.node_list],
            node_y=[graph.nodes[node]["y"] for node in self.node_list],
            node_betweenness=[
                graph.nodes[node]["node_betweenness_normal"] for node in self.node_list
            ],
            percentile=percentile / 100,
        )

    def __str__(self):
        """Return a string representation of the metric object.

        Only returns the attributes that are not None or for a dict the
        attributes that are not None for each key. If all attributes in a dict are None,
        it is not returned.
        If no attributes are not None, an empty string is returned.
        """
        string = ""
        for key, value in self.__dict__.items():
            if value is not None or key == "unit":
                if isinstance(value, dict):
                    if all(v is None for v in value.values()):
                        continue
                    string += f"{key}: "
                    for key2, value2 in value.items():
                        if value2 is not None:
                            string += f"{key2}: {value2}, "
                    string = string[:-2] + "; "
                else:
                    string += f"{key}: {value}; "
        return string

    def __repr__(self):
        """Return a string representation of the metric object.

        Additional to the __str__ method, it also returns the class name.
        """
        return f"{self.__class__.__name__}({self.__str__()})"

    def __eq__(self, other):
        """Return True if the two objects are equal.

        Tests the equality of the attributes of the objects.
        Used in input-output tests.
        """
        return compare_dicts(self.__dict__, other.__dict__)

    def save(self, folder, name):
        """Save the metric to a file.

        Will be saved as a pickle file at folder/name.metrics.

        Parameters
        ----------
        folder : str
            The folder to save the metric to.
        name : str
            The name of the file to save the metric to.

        """

        metrics_path = join(folder, name + ".metrics")
        # Check if metrics already exist
        if exists(metrics_path):
            logger.debug("Metrics already exist, overwriting %s", metrics_path)
        else:
            logger.debug("Saving metrics to %s", metrics_path)
        with open(metrics_path, "wb") as file:
            pickle.dump(self, file)

    @classmethod
    def load(cls, name):
        """Load a partitioning from a file.

        Parameters
        ----------
        path : str
            The path to the file to load the partitioning from.

        Returns
        -------
        partitioning : Partitioning
            The loaded partitioning.

        """

        metrics_path = join(RESULTS_DIR, name, name + ".metrics")
        logger.debug("Loading metrics from %s", metrics_path)
        with open(metrics_path, "rb") as file:
            metrics = pickle.load(file)

        return metrics
