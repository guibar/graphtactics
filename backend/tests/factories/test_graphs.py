from graphtactics.road_network_factory import RoadNetworkFactory


def test_get_graph_st_quentin():
    factory = RoadNetworkFactory()
    network = factory.create("st_quentin")
    inner_nodes = [node for node, data in network.graph.nodes.items() if data["inner"]]
    inner_edges = [e for e in network.graph.edges if e[0] in inner_nodes and e[1] in inner_nodes]

    assert len(network.graph.nodes) == 185
    assert len(inner_nodes) == 17

    assert len(network.graph.edges) == 347
    assert len(inner_edges) == 25
    assert network.boundary_buff.contains(network.boundary)
    assert network.graph.nodes[661039949]["inner"]
    assert not network.graph.nodes[1637478842]["inner"]


def test_get_graph_and_noailles():
    factory = RoadNetworkFactory()
    network = factory.create("noailles")
    inner_nodes = [node for node, data in network.graph.nodes.items() if data["inner"]]
    inner_edges = [e for e in network.graph.edges if e[0] in inner_nodes and e[1] in inner_nodes]
    assert len(network.graph.nodes) == 668
    assert len(inner_nodes) == 105

    assert len(network.graph.edges) == 1300
    assert len(inner_edges) == 229
    assert network.boundary_buff.contains(network.boundary)
    assert network.graph.nodes[3437132134]["inner"]
    assert not network.graph.nodes[1614109421]["inner"]


def test_get_graph_and_df_d2():
    factory = RoadNetworkFactory()
    network = factory.create("d2")
    inner_nodes = [node for node, data in network.graph.nodes.items() if data["inner"]]
    inner_edges = [e for e in network.graph.edges if e[0] in inner_nodes and e[1] in inner_nodes]

    assert len(network.graph.nodes) == 1156
    assert len(inner_nodes) == 759

    assert len(network.graph.edges) == 2147
    assert len(inner_edges) == 1317
    assert network.boundary_buff.contains(network.boundary)
    assert network.graph.nodes[2447852537]["inner"]
    assert not network.graph.nodes[661117435]["inner"]


def test_get_graph_and_df_60():
    factory = RoadNetworkFactory()
    network = factory.create("60")
    inner_nodes = [node for node, data in network.graph.nodes.items() if data["inner"]]
    inner_edges = [e for e in network.graph.edges if e[0] in inner_nodes and e[1] in inner_nodes]

    assert len(network.graph.nodes) == 9363
    assert len(inner_nodes) == 6416

    assert len(network.graph.edges) == 18664
    assert len(inner_edges) == 12596
    assert network.boundary_buff.contains(network.boundary)
    assert network.graph.nodes[888460718]["inner"]
    assert not network.graph.nodes[665087395]["inner"]
