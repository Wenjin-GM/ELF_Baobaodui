from setuptools import setup

package_name = "smart_cabinet_nodes"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="elf",
    maintainer_email="elf@example.com",
    description="ROS2 Python nodes for the smart tool cabinet.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "env_node = smart_cabinet_nodes.env_node:main",
            "actuator_node = smart_cabinet_nodes.actuator_node:main",
            "nfc_node = smart_cabinet_nodes.nfc_node:main",
            "nfc_action_client = smart_cabinet_nodes.nfc_action_client:main",
            "face_node = smart_cabinet_nodes.face_node:main",
            "cabinet_logic_node = smart_cabinet_nodes.cabinet_logic_node:main",
            "ui_node = smart_cabinet_nodes.ui_node:main",
            "console_monitor = smart_cabinet_nodes.console_monitor:main",
            "scenario_player = smart_cabinet_nodes.scenario_player:main",
            "battery_node = smart_cabinet_nodes.battery_node:main",
            "vision_node = smart_cabinet_nodes.vision_node:main",
        ],
    },
)
