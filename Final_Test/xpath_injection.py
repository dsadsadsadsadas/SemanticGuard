import xml.etree.ElementTree as ET
def get_user(xml_data, username):
    root = ET.fromstring(xml_data)
    # VULNERABLE: XPath Injection appending untrusted input
    return root.find(f"./users/user[name='{username}']")
