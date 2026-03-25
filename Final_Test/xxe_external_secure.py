from lxml import etree
def parse_xml(xml_content):
    # SAFE: XXE Defense by disabling entity resolution and network
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    return etree.fromstring(xml_content, parser)
