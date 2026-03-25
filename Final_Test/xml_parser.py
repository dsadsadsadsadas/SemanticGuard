# XML Parser
import xml.etree.ElementTree as ET

def parse_xml_data(xml_string):
    # VULNERABLE: XXE - no defusedxml
    root = ET.fromstring(xml_string)
    return root.findall('.//data')
