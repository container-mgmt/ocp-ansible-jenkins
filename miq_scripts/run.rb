print "Assinging alert profiles to the Enterprise\n"

MiqAlertSet.find_by(:guid=>"a16fcf51-e2ae-492d-af37-19de881476ad").assign_to_objects(MiqEnterprise.last)
MiqAlertSet.find_by(:guid=>"ff0fb114-be03-4685-bebb-b6ae8f13d7ad").assign_to_objects(MiqEnterprise.last)
