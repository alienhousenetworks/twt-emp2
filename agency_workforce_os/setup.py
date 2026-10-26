from setuptools import setup, find_packages

setup(
    name="agency_workforce_os",
    version="0.1.0",
    description="Agency Workforce OS custom Frappe app",
    author="AlienHouse Networks",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
)
