from config import config_helper as config
config.set_mode('debug')
import gem_data

css_str = """a[href$="#support-gem-red"],
a[href$="#support-gem-green"],
a[href$="#support-gem-blue"],
a[href$="#support-gem-white"] {
    padding: 1px 4px;
    display: inline-block;
    color: white !important;
    background-color: #666;
    text-align: center;
    vertical-align: middle;
    font-size: 1rem;
    font-family: Verdana,Arial,Helvetica,sans-serif;
    text-shadow: -1px 0 black, 0 1px black, 1px 0 black, 0 -1px black;
    white-space: nowrap;  
}

a[href$="#support-gem-red"],
a[href$="#support-gem-red"]:hover:before {
    background-color: #c51e1e;
}

a[href$="#support-gem-green"],
a[href$="#support-gem-green"]:hover:before {
    background-color: #08a842;
}

a[href$="#support-gem-blue"],
a[href$="#support-gem-blue"]:hover:before {
    background-color: #4163c9;
}

a[href$="#support-gem-white"],
a[href$="#support-gem-white"]:hover:before {
    background-color: #ffffff;
}

a[href$="#support-gem-red"]:hover:before,
a[href$="#support-gem-green"]:hover:before,
a[href$="#support-gem-blue"]:hover:before,
a[href$="#support-gem-white"]:hover:before {
   position: absolute;
   margin-top: -25px;
   padding: 1px 3px;
   z-index: 1;
}
"""

gem_template = """
a[href$="{:s}#support-gem-{:s}"]:hover:before {{ content: "{:s}"; }}"""

for k in gem_data.support_gems:
	gem = gem_data.support_gems[k]
	
	if not gem.is_support:
		continue
		
	if gem.json['base_item'] is None:
		continue
		
	if gem.json['base_item']['release_state'] != "released":
		continue
	
	css_str += gem_template.format(gem.get_url_suffix(), gem.get_color_str(), gem.short_name)
	
out = "data\support_gems.css"

with open(out, "w") as f:
	f.write(css_str)
	
print(("Gem CSS written to {}".format(out)))