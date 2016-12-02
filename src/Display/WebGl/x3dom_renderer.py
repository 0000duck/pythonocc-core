##Copyright 2011-2016 Thomas Paviot (tpaviot@gmail.com)
##
##This file is part of pythonOCC.
##
##pythonOCC is free software: you can redistribute it and/or modify
##it under the terms of the GNU Lesser General Public License as published by
##the Free Software Foundation, either version 3 of the License, or
##(at your option) any later version.
##
##pythonOCC is distributed in the hope that it will be useful,
##but WITHOUT ANY WARRANTY; without even the implied warranty of
##MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##GNU Lesser General Public License for more details.
##
##You should have received a copy of the GNU Lesser General Public License
##along with pythonOCC.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function

import os
import tempfile

from OCC.Visualization import Tesselator
from OCC.gp import gp_Vec
from OCC import VERSION as OCC_VERSION

from simple_server import start_server

HEADER = """
<head>
    <title>pythonOCC @VERSION@ x3dom renderer</title>
    <meta name='Author' content='Thomas Paviot - tpaviot@gmail.com'>
    <meta name='Keywords' content='WebGl,pythonOCC'>
    <meta charset="utf-8">
    <link rel="stylesheet" type="text/css" href="http://x3dom.org/release/x3dom.css" charset="utf-8" ></link>
    <script type="text/javascript" src="http://x3dom.org/release/x3dom-full.js"></script>
    <script type="text/javascript" src="http://code.jquery.com/jquery-2.1.0.min.js" ></script>
    <style type="text/css">
        body {
            background: linear-gradient(@bg_gradient_color1@, @bg_gradient_color2@);
            margin: 0px;
            overflow: hidden;
        }
        #pythonocc_rocks {
            padding: 5px;
            position: absolute;
            left: 1%;
            top: 85%;
            height: 60px;
            width: 305px;
            border-radius: 5px;
            border: 2px solid #f7941e;
            opacity: 0.7;
            font-family: Arial;
            background-color: #414042;
            color: #ffffff;
            font-size: 16px;
            opacity: 0.7;
        }
        #selection_info {
            padding: 5px;
            position: absolute;
            left: 85%;
            top: 1%;
            height: 22px;
            width: 200px;
            border-radius: 5px;
            border: 2px solid #f7941e;
            opacity: 0.7;
            font-family: Arial;
            background-color: #414042;
            color: #ffffff;
            font-size: 16px;
            opacity: 0.7;
        }
        a {
            color: #f7941e;
            text-decoration: none;
        }
        a:hover {
            color: #ffffff;
        }
    </style>
</head>
"""

BODY = """
<body>
    <div id="x3d_scene">@X3DSCENE@</div>
    <div id="pythonocc_rocks">
        <b>pythonOCC @VERSION@ <a href="htpp://www.x3dom.org" target="_blank">x3dom</a> renderer</b><hr>
        Check our blog at
        <a style="font-size:14px;" href=http://www.pythonocc.org>http://www.pythonocc.org</a>
    </div>
    <div id="selection_info">
        <input type="button" value="Fit All" onclick="fitAll();">
    </div>
    <script>
    function fitAll(){
        document.getElementsByTagName('x3d')[0].runtime.showAll();
    }
    </script>
</body>
"""


def ExportEdgeToILS(edge_point_set):
    str_x3d_to_return = "\t<LineSet vertexCount='%i' lit='false' solid='false' pickable='false'>" % len(edge_point_set)
    str_x3d_to_return += "<Coordinate point='"
    for p in edge_point_set:
        str_x3d_to_return += "%g %g %g " % (p[0], p[1], p[2])
    str_x3d_to_return += "'/></LineSet>\n"
    return str_x3d_to_return


class HTMLHeader(object):
    def __init__(self, bg_gradient_color1="#ced7de", bg_gradient_color2="#808080"):
        self._bg_gradient_color1 = bg_gradient_color1
        self._bg_gradient_color2 = bg_gradient_color2


    def get_str(self):
        header_str = HEADER.replace('@bg_gradient_color1@', '%s' % self._bg_gradient_color1)
        header_str = header_str.replace('@bg_gradient_color2@', '%s' % self._bg_gradient_color2)
        header_str = header_str.replace('@VERSION@', OCC_VERSION)
        return header_str


class HTMLBody(object):
    def __init__(self, x3d_shapes_dict):
        self._x3d_shapes_dict = x3d_shapes_dict

    def get_str(self):
        # get the location where pythonocc is running from
        body_str = BODY.replace('@VERSION@', OCC_VERSION)
        x3dcontent = '\n<x3d style="width:100%;border: none" >\n<scene>\n'
        for shp in self._x3d_shapes_dict:
            trans, ori = self._x3d_shapes_dict[shp]
            vx, vy, vz = trans
            ori_vx, ori_vy, ori_vz, angle = ori
            x3dcontent += '\t\t<inline mapDEFToID="true" url="shp%s.x3d"></inline>\n' % shp
        x3dcontent += "</scene>\n</x3d>\n"
        body_str = body_str.replace('@X3DSCENE@', x3dcontent)
        return body_str


class X3DExporter(object):
    """ A class for exporting a TopoDS_Shape to an x3d file """
    def __init__(self,
                 shape,  # the TopoDS shape to mesh
                 vertex_shader,  # the vertex_shader, passed as a string
                 fragment_shader,  # the fragment shader, passed as a string
                 export_edges,  # if yes, edges are exported to IndexedLineSet (might be SLOWW)
                 color,  # the default shape color
                 specular_color,  # shape specular color (white by default)
                 shininess,  # shape shininess
                 transparency,  # shape transparency
                 line_color,  # edge color
                 line_width,  # edge liewidth,
                 mesh_quality  # mesh quality default is 1., good is <1, bad is >1
                ):
        self._shape = shape
        self._vs = vertex_shader
        self._fs = fragment_shader
        self._export_edges = export_edges
        self._color = color
        self._shininess = shininess
        self._specular_color = specular_color
        self._transparency = transparency
        self._mesh_quality = mesh_quality
        # the list of indexed face sets that compose the shape
        # if ever the map_faces_to_mesh option is enabled, this list
        # maybe composed of dozains of IndexedFaceSet
        self._indexed_face_sets = []
        self._indexed_line_sets = []

    def compute(self):
        shape_tesselator = Tesselator(self._shape)
        shape_tesselator.Compute(compute_edges=self._export_edges,
        	                     mesh_quality=self._mesh_quality)
        self._indexed_face_sets.append(shape_tesselator.ExportShapeToX3DIndexedFaceSet())
        # then process edges
        if self._export_edges:
            # get number of edges
            nbr_edges = shape_tesselator.ObjGetEdgeCount()
            for i_edge in range(nbr_edges):
                edge_point_set = []
                nbr_vertices = shape_tesselator.ObjEdgeGetVertexCount(i_edge)
                for i_vert in range(nbr_vertices):
                    edge_point_set.append(shape_tesselator.GetEdgeVertex(i_edge, i_vert))
                ils = ExportEdgeToILS(edge_point_set)
                self._indexed_line_sets.append(ils)

    def write_to_file(self, filename):
        # write header
        f = open(filename, "w")
        f.write("""<?xml version="1.0" encoding="UTF-8"?>
<X3D style="width:100%;border: none" profile="Immersive" version="3.2" xmlns:xsd="http://www.w3.org/2001/XMLSchema-instance" xsd:noNamespaceSchemaLocation="http://www.web3d.org/specifications/x3d-3.2.xsd">
<head>
    <meta name="generator" content="pythonOCC X3D exporter (www.pythonocc.org)"/>
</head>
<Scene>
        """)
        shape_id = 0
        for indexed_face_set in self._indexed_face_sets:
            f.write('<Shape DEF="shape%i"><Appearance>\n' % shape_id)
            #
            # set Material or shader
            #
            if self._vs is None and self._fs is None:
                f.write("<Material diffuseColor=")
                f.write("'%g %g %g'" % (self._color[0],
                                        self._color[1],
                                        self._color[2]))
                f.write(" shininess=")
                f.write("'%g'" % self._shininess)
                f.write(" specularColor=")
                f.write("'%g %g %g'" % (self._specular_color[0],
                                        self._specular_color[1],
                                        self._specular_color[2]))
                f.write(" transparency='%g'>\n" % self._transparency)
                f.write("</Material>\n")
            else:  # set shaders
                f.write('<ComposedShader><ShaderPart type="VERTEX" style="display:none;">\n')
                f.write(self._vs)
                f.write('</ShaderPart>\n')
                f.write('<ShaderPart type="FRAGMENT" style="display:none;">\n')
                f.write(self._fs)
                f.write('</ShaderPart></ComposedShader>\n')
            f.write('</Appearance>\n')
            # export triangles
            f.write(indexed_face_set)
            f.write("</Shape>\n")
            shape_id += 1
        # and now, process edges
        edge_id = 0
        for indexed_line_set in self._indexed_line_sets:
            f.write('<Shape DEF="edg%i">' % edge_id)
            f.write(indexed_line_set)
            f.write("</Shape>\n")
            edge_id += 1
        f.write('</Scene>\n</X3D>\n')
        f.close()


class X3DomRenderer(object):
    def __init__(self, path=None):
        if not path:  # by default, write to a temp directory
            self._path = tempfile.mkdtemp()
        else:
            self._path = path
        self._html_filename = os.path.join(self._path, 'index.html')
        self._x3d_shapes = {}
        print("X3DomRenderer initiliazed. Waiting for shapes to be added to the buffer.")

    def DisplayShape(self,
                     shape,
                     vertex_shader=None,
                     fragment_shader=None,
                     export_edges=False,
                     color=(0.65, 0.65, 0.65),
                     specular_color=(1, 1, 1),
                     shininess=0.9,
                     transparency=0.,
                     line_color=(0, 0., 0.),
                     line_width=2.,
                     mesh_quality=1.):
        """ Adds a shape to the rendering buffer. This class computes the x3d file
        """
        shape_hash = hash(shape)
        x3d_exporter = X3DExporter(shape, vertex_shader, fragment_shader,
                                   export_edges, color,
                                   specular_color, shininess, transparency,
                                   line_color, line_width, mesh_quality)
        x3d_exporter.compute()
        x3d_filename = os.path.join(self._path, "shp%s.x3d" % shape_hash)
        # the x3d filename is computed from the shape hash
        x3d_exporter.write_to_file(x3d_filename)
        # get shape translation and orientation
        trans = shape.Location().Transformation().TranslationPart().Coord()  # vector
        v = gp_Vec()
        angle = shape.Location().Transformation().GetRotation().GetVectorAndAngle(v)
        ori = (v.X(), v.Y(), v.Z(), angle)  # angles
        # fill the shape dictionnary with shape hash, translation and orientation
        self._x3d_shapes[shape_hash] = [trans, ori]

    def render(self, server_port=8080):
        """ Call the render() method to display the X3D scene.
        """
        # log path
        print("Files written to %s" % self._path)
        # first generate the HTML root file
        self.GenerateHTMLFile()
        # then create a simple web server
        os.chdir(self._path)
        print("## Serving at port", server_port, "using SimpleHTTPServer")
        print("## Open your webbrowser at the URL: http://localhost:%i" % server_port)
        print("## CTRL-C to shutdown the server")
        start_server(server_port)


    def GenerateHTMLFile(self):
        """ Generate the HTML file to be rendered wy the web browser
        """
        print("File written to %s" % self._path)
        fp = open(self._html_filename, "w")
        fp.write("<!DOCTYPE HTML>")
        fp.write('<html lang="en">')
        # header
        fp.write(HTMLHeader().get_str())
        # body
        fp.write(HTMLBody(self._x3d_shapes).get_str())
        fp.write("</html>\n")
        fp.close()

def translate_topods_from_vector(brep_or_iterable, vec, copy=False):
    '''
    translate a brep over a vector
    @param brep:    the Topo_DS to translate
    @param vec:     the vector defining the translation
    @param copy:    copies to brep if True
    '''
    from OCC.gp import gp_Trsf
    from OCC.BRepBuilderAPI import BRepBuilderAPI_Transform
    trns = gp_Trsf()
    trns.SetTranslation(vec)
    brep_trns = BRepBuilderAPI_Transform(brep_or_iterable, trns, copy)
    shp = brep_trns.Shape()
    return shp

def rotate_shape_3_axis(shape, rx, ry, rz, unite="deg"):
    """ Rotate a shape around (O,x), (O,y) and (O,z).

    @param rx_degree : rotation around (O,x)
    @param ry_degree : rotation around (O,y)
    @param rz_degree : rotation around (O,z)

    @return : the rotated shape.
    """
    from math import radians
    from OCC.gp import gp_OX, gp_OY, gp_OZ
    from OCC.gp import gp_Trsf
    from OCC.BRepBuilderAPI import BRepBuilderAPI_Transform

    if unite == "deg":  # convert angle to radians
        rx = radians(rx)
        ry = radians(ry)
        rz = radians(rz)
    alpha = gp_Trsf()
    alpha.SetRotation(gp_OX(), rx)
    beta = gp_Trsf()
    beta.SetRotation(gp_OY(), ry)
    gamma = gp_Trsf()
    gamma.SetRotation(gp_OZ(), rz)
    brep_trns = BRepBuilderAPI_Transform(shape, alpha*beta*gamma, False)
    shp = brep_trns.Shape()
    return shp

if __name__ == "__main__":
    from OCC.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeTorus, BRepPrimAPI_MakeSphere
    # the simpliest example
    from OCC.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeTorus
    #box = BRepPrimAPI_MakeBox(1., 2., 3.).Shape()
    #shp = BRepPrimAPI_MakeTorus(20., 10.).Shape()
    #my_ren = X3DomRenderer()
    #my_ren.DisplayShape(box, export_edges=True)
    #my_ren.DisplayShape(shp, export_edges=True)
    #my_ren.render()
    # box_shp = BRepPrimAPI_MakeBox(10., 20., 30.).Shape()
    # rotated_box = rotate_shape_3_axis(box_shp, 45,0,0,'deg')
    # torus_shp = BRepPrimAPI_MakeTorus(20., 10.).Shape()
    # sphere_shp = BRepPrimAPI_MakeSphere(2).Shape()
    my_ren = X3DomRenderer()
    # my_ren.DisplayShape(rotated_box, shape_color=(0.8,0.1,0.1), export_edges=True)
    # my_ren.DisplayShape(torus_shp, export_edges=False)
    # my_ren.DisplayShape(translate_topods_from_vector(sphere_shp, gp_Vec(1,0,0)), export_edges=False)
    # my_ren.render()
    # a cool example just to show asynchronous load:
    #
    import random
    for i in range(100):
        box_shp = BRepPrimAPI_MakeBox(random.random()*20, random.random()*20, random.random()*20).Shape()
        # random position and orientation and color
        angle_x = random.random()*360
        angle_y = random.random()*360
        angle_z = random.random()*360
        rotated_box = rotate_shape_3_axis(box_shp, angle_x, angle_y, angle_z, 'deg')
        tr_x = random.uniform(-10, 10)
        tr_y = random.uniform(-10, 10)
        tr_z = random.uniform(-10, 10)
        trans_box = translate_topods_from_vector(rotated_box, gp_Vec(tr_x, tr_y, tr_z))
        rnd_color = (random.random(), random.random(), random.random())
        my_ren.DisplayShape(trans_box, export_edges=True, color=rnd_color, transparency=random.random())
    my_ren.render()
