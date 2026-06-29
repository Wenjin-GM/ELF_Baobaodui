cmake_minimum_required(VERSION 3.8)
project(smart_cabinet_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "action/ReadNfcCard.action"
  "action/AuthenticateFace.action"
  "action/RunInventory.action"
  "srv/OpenLock.srv"
  "srv/SetFan.srv"
  "srv/Beep.srv"
  "srv/RequestOpen.srv"
  "srv/RequestInventory.srv"
  "srv/RequestManualFan.srv"
  "srv/RequestTempUnlock.srv"
  "srv/UpdateEnvThresholds.srv"
  DEPENDENCIES builtin_interfaces std_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
