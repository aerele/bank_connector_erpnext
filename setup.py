from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in bank_connector_erpnext/__init__.py
from bank_connector_erpnext import __version__ as version

setup(
	name="bank_connector_erpnext",
	version=version,
	description="ERPNext - Bank Connector",
	author="Aerele Technologies Private Limited",
	author_email="hello@aerele.in",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
