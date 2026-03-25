from lxml import etree
def parse_xml(xml_content):
    # VULNERABLE: XXE parsing with external network entities enabled
    parser = etree.XMLParser(resolve_entities=True, no_network=False)
    return etree.fromstring(xml_content, parser)
