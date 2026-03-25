# Secure XML Parser
import defusedxml.ElementTree as ET

def parse_xml_data(xml_string: str):
    """Parse XML safely with defusedxml"""
    # SECURE: defusedxml prevents XXE attacks
    root = ET.fromstring(xml_string)
    return root.findall('.//data')

def parse_xml_file(filepath: str):
    """Parse XML file safely"""
    tree = ET.parse(filepath)
    return tree.getroot()
