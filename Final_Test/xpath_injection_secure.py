import xml.etree.ElementTree as ET
def get_user(xml_data, username):
    root = ET.fromstring(xml_data)
    # SAFE: Iterating nodes safely rather than dynamic XPath queries
    for user in root.findall('./users/user'):
        if user.find('name').text == username:
            return user
    return None
