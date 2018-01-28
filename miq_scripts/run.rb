puts "Assinging alert profiles to the Enterprise"

MiqAlertSet.find_by(:guid=>"a16fcf51-e2ae-492d-af37-19de881476ad").assign_to_objects(MiqEnterprise.last)
MiqAlertSet.find_by(:guid=>"ff0fb114-be03-4685-bebb-b6ae8f13d7ad").assign_to_objects(MiqEnterprise.last)

puts "Enabling C&U roles"

server_config = MiqServer.my_server.get_config()
roles = server_config.config[:server][:role].split(',')
roles += ['ems_metrics_collector','ems_metrics_coordinator','ems_metrics_processor']
roles = roles.sort().join(',')
MiqServer.my_server.set_config(:server=>{:role => roles})
MiqServer.my_server.save()
