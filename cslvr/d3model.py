from dolfin            import *
from dolfin_adjoint    import *
from cslvr.inputoutput import print_text, get_text, print_min_max
from cslvr.model       import Model
from cslvr.helper      import Boundary
from scipy.spatial     import cKDTree
from copy              import copy
import numpy               as np
import matplotlib.pyplot   as plt
import sys, os

class D3Model(Model):
  """ 
  """
  OMEGA_GND   = 0   # internal cells over bedrock
  OMEGA_FLT   = 1   # internal cells over water
  GAMMA_S_GND = 2   # grounded upper surface
  GAMMA_B_GND = 3   # grounded lower surface (bedrock)
  GAMMA_S_FLT = 6   # shelf upper surface
  GAMMA_B_FLT = 5   # shelf lower surface
  GAMMA_L_DVD = 7   # basin divides
  GAMMA_L_OVR = 4   # terminus over water
  GAMMA_L_UDR = 10  # terminus under water
  GAMMA_U_GND = 8   # grounded surface with U observations
  GAMMA_U_FLT = 9   # shelf surface with U observations
  GAMMA_ACC   = 1   # areas with positive surface accumulation

  # external boundaries :
  ext_boundaries = {GAMMA_S_GND : 'grounded upper surface',
                    GAMMA_B_GND : 'grounded lower surface (bedrock)',
                    GAMMA_S_FLT : 'shelf upper surface',
                    GAMMA_B_FLT : 'shelf lower surface',
                    GAMMA_L_DVD : 'basin divides',
                    GAMMA_L_OVR : 'terminus over water',
                    GAMMA_L_UDR : 'terminus under water',
                    GAMMA_U_GND : 'grounded upper surface with U observations',
                    GAMMA_U_FLT : 'shelf upper surface with U observations',
                    GAMMA_ACC   : 'upper surface with accumulation'}

  # internal boundaries :
  int_boundaries = {OMEGA_GND   : 'internal cells located over bedrock',
                    OMEGA_FLT   : 'internal cells located over water'}

  # union :
  boundaries = {'OMEGA' : int_boundaries,
                'GAMMA' : ext_boundaries}

  def __init__(self, mesh, out_dir='./results/', order=1, 
               use_periodic=False):
    """
    A three-dimensional model.
    """
    s = "::: INITIALIZING 3D MODEL :::"
    print_text(s, cls=self)
    
    Model.__init__(self, mesh, out_dir, order, use_periodic)
  
  def color(self):
    return '130'

  def generate_pbc(self):
    """
    return a SubDomain of periodic lateral boundaries.
    """
    s = "    - using 3D periodic boundaries -"
    print_text(s, cls=self)

    xmin = MPI.min(mpi_comm_world(), self.mesh.coordinates()[:,0].min())
    xmax = MPI.max(mpi_comm_world(), self.mesh.coordinates()[:,0].max())
    ymin = MPI.min(mpi_comm_world(), self.mesh.coordinates()[:,1].min())
    ymax = MPI.max(mpi_comm_world(), self.mesh.coordinates()[:,1].max())
    
    class PeriodicBoundary(SubDomain):
      
      def inside(self, x, on_boundary):
        """
        Return True if on left or bottom boundary AND NOT on one 
        of the two corners (0, 1) and (1, 0).
        """
        return bool((near(x[0], xmin) or near(x[1], ymin)) and \
                    (not ((near(x[0], xmin) and near(x[1], ymax)) \
                     or (near(x[0], xmax) and near(x[1], ymin)))) \
                     and on_boundary)

      def map(self, x, y):
        """
        Remap the values on the top and right sides to the bottom and left
        sides.
        """
        if near(x[0], xmax) and near(x[1], ymax):
          y[0] = x[0] - xmax
          y[1] = x[1] - ymax
          y[2] = x[2]
        elif near(x[0], xmax):
          y[0] = x[0] - xmax
          y[1] = x[1]
          y[2] = x[2]
        elif near(x[1], ymax):
          y[0] = x[0]
          y[1] = x[1] - ymax
          y[2] = x[2]
        else:
          y[0] = x[0]
          y[1] = x[1]
          y[2] = x[2]

    self.pBC = PeriodicBoundary()
  
  def set_mesh(self, mesh):
    """
    Sets the mesh.
    
    :param mesh : Dolfin mesh to be written
    """
    super(D3Model, self).set_mesh(mesh)
    
    s = "::: setting 3D mesh :::"
    print_text(s, cls=self)
    
    self.mesh.init(1,2)
    if self.dim != 3:
      s = ">>> 3D MODEL REQUIRES A 3D MESH, EXITING <<<"
      print_text(s, 'red', 1)
      sys.exit(1)
    else:
      self.num_facets   = self.mesh.num_facets()
      self.num_cells    = self.mesh.num_cells()
      self.num_vertices = self.mesh.num_vertices()
    s = "    - %iD mesh set, %i cells, %i facets, %i vertices - " \
        % (self.dim, self.num_cells, self.num_facets, self.num_vertices)
    print_text(s, cls=self)
  
  def set_flat_mesh(self, flat_mesh):
    """
    Sets the flat_mesh for 3D free-surface.
    
    :param flat_mesh : Dolfin mesh to be written
    """
    s = "::: setting 3D ``flat'' mesh :::"
    print_text(s, cls=self)

    self.flat_mesh = flat_mesh
    self.flat_dim  = self.flat_mesh.ufl_cell().topological_dimension()
    if self.flat_dim != 3:
      s = ">>> 3D MODEL REQUIRES A 3D FLAT_MESH, EXITING <<<"
      print_text(s, 'red', 1)
      sys.exit(1)

  def set_srf_mesh(self, srfmesh):
    """
    Set the surface boundary mesh.
    """
    s = "::: setting surface boundary mesh :::"
    print_text(s, cls=self)

    if isinstance(srfmesh, dolfin.cpp.io.HDF5File):
      self.srfmesh = Mesh()
      srfmesh.read(self.srfmesh, 'srfmesh', False)

    elif isinstance(srfmesh, dolfin.cpp.mesh.Mesh):
      self.srfmesh = srfmesh

  def set_bed_mesh(self, bedmesh):
    """
    Set the basal boundary mesh.
    """
    s = "::: setting basal boundary mesh :::"
    print_text(s, cls=self)

    if isinstance(bedmesh, dolfin.cpp.io.HDF5File):
      self.bedmesh = Mesh()
      bedmesh.read(self.bedmesh, 'bedmesh', False)

    elif isinstance(bedmesh, dolfin.cpp.mesh.Mesh):
      self.bedmesh = bedmesh

  def set_lat_mesh(self, latmesh):
    """
    Set the lateral boundary mesh.
    """
    s = "::: setting lateral boundary mesh :::"
    print_text(s, cls=self)

    if isinstance(latmesh, dolfin.cpp.io.HDF5File):
      self.latmesh = Mesh()
      latmesh.read(self.latmesh, 'latmesh', False)

    elif isinstance(latmesh, dolfin.cpp.mesh.Mesh):
      self.latmesh = latmesh

    self.Q_lat = FunctionSpace(self.latmesh, 'CG', 1)

  def set_dvd_mesh(self, dvdmesh):
    """
    Set the lateral divide boundary mesh.
    """
    s = "::: setting lateral divide boundary mesh :::"
    print_text(s, cls=self)

    if isinstance(dvdmesh, dolfin.cpp.io.HDF5File):
      self.dvdmesh = Mesh()
      dvdmesh.read(self.dvdmesh, 'dvdmesh', False)

    elif isinstance(dvdmesh, dolfin.cpp.mesh.Mesh):
      self.dvdmesh = dvdmesh

    self.Q_dvd = FunctionSpace(self.dvdmesh, 'CG', 1)

  def form_srf_mesh(self):
    """
    sets self.srfmesh, the surface boundary mesh for this model instance.
    """
    s = "::: extracting surface mesh :::"
    print_text(s, cls=self)

    bmesh   = BoundaryMesh(self.mesh, 'exterior')
    cellmap = bmesh.entity_map(2)
    pb      = MeshFunction("size_t", bmesh, 2, 0)
    for c in cells(bmesh):
      if Facet(self.mesh, cellmap[c.index()]).normal().z() > 1e-3:
        pb[c] = 1
    submesh = SubMesh(bmesh, pb, 1)
    self.srfmesh = submesh

  def form_bed_mesh(self):
    """
    sets self.bedmesh, the basal boundary mesh for this model instance.
    """
    s = "::: extracting bed mesh :::"
    print_text(s, cls=self)

    bmesh   = BoundaryMesh(self.mesh, 'exterior')
    cellmap = bmesh.entity_map(2)
    pb      = MeshFunction("size_t", bmesh, 2, 0)
    for c in cells(bmesh):
      if Facet(self.mesh, cellmap[c.index()]).normal().z() < -1e-3:
        pb[c] = 1
    submesh = SubMesh(bmesh, pb, 1)
    self.bedmesh = submesh

  def form_lat_mesh(self):
    """
    sets self.latmesh, the lateral boundary mesh for this model instance.
    """
    s = "::: extracting lateral mesh :::"
    print_text(s, cls=self)

    bmesh   = BoundaryMesh(self.mesh, 'exterior')
    cellmap = bmesh.entity_map(2)
    pb      = MeshFunction("size_t", bmesh, 2, 0)
    for c in cells(bmesh):
      if abs(Facet(self.mesh, cellmap[c.index()]).normal().z()) < 1e-3:
        pb[c] = 1
    submesh = SubMesh(bmesh, pb, 1)
    self.latmesh = submesh

  def form_dvd_mesh(self, contour):
    """
    sets self.dvdmesh, the lateral divide boundary mesh for this model instance.

    :param contour: NumPy array of exterior points to exclude.
    :type contour:  :class:`numpy.ndarray`
    """
    s = "::: extracting lateral divide mesh :::"
    print_text(s, cls=self)
      
    tree = cKDTree(contour)

    bmesh   = BoundaryMesh(self.mesh, 'exterior')
    cellmap = bmesh.entity_map(2)
    pb      = MeshFunction("size_t", bmesh, 2, 0)
    for c in cells(bmesh):
      f       = Facet(self.mesh, cellmap[c.index()])
      n       = f.normal()
      x_m     = f.midpoint().x()
      y_m     = f.midpoint().y()
      z_m     = f.midpoint().z()
      if abs(n.z()) < 1e-3 and tree.query((x_m, y_m))[0] > 1000:
        pb[c] = 1
    submesh = SubMesh(bmesh, pb, 1)
    self.dvdmesh = submesh

  def generate_function_spaces(self):
    """
    Generates the appropriate finite-element function spaces from parameters
    specified in the config file for the model.
    """
    super(D3Model, self).generate_function_spaces()

    s = "::: generating 3D function spaces :::"
    print_text(s, cls=self)
    
    if self.use_periodic:
      self.Q4    = FunctionSpace(self.mesh, self.QM4e,
                                 constrained_domain=self.pBC)
      self.QTH3  = FunctionSpace(self.mesh, self.QTH3e,
                                 constrained_domain=self.pBC)
    
    s = "    - 3D function spaces created - "
    print_text(s, cls=self)

  def generate_submesh_to_mesh_map(self, sub_model):
    r"""
    Create a map from each of the functionspaces defined in this model with the
    submesh model ``sub_model``. 
    """
    # TODO: for now, only works for linear elements.
    
    bmesh   = BoundaryMesh(self.mesh, "exterior") # surface boundary mesh
    vertmap = bmesh.entity_map(0)                 # map from bmesh to mesh
    submesh = sub_model.mesh                      # get the submesh
    m       = vertex_to_dof_map(self.Q)
    si      = dof_to_vertex_map(sub_model.Q)
    t       = submesh.data().array('parent_vertex_indices', 0)

    # form the map from submesh dof to mesh dof :
    mesh_vertices = []
    for sub_dof in range(sub_model.Q.dim()):
      submesh_vertex     = si[sub_dof]
      boundary_vertex    = t[submesh_vertex]
      mesh_vertex        = vertmap[int(boundary_vertex)] # np.uint not accepted
      mesh_vertices.append(mesh_vertex)
    Q_to_Qs_dofmap       = m[mesh_vertices]

    self.submesh_map_dict = {'Q' : Q_to_Qs_dofmap}
    sub_model.assign_variable(sub_model.Q_to_Qs_dofmap, Q_to_Qs_dofmap)

  def set_submesh_to_mesh_map(self, sub_model):
    r"""
    """
    Q_to_Qs_dofmap = sub_model.Q_to_Qs_dofmap.vector().get_local().astype('int')
    self.submesh_map_dict = {'Q' : Q_to_Qs_dofmap}

  def assign_from_submesh_variable(self, u, u_sub):
    r"""
    Assign the values from the variable ``u_sub`` defined on a submesh of 
    this :class:`~model.Model`'s mesh to the variable ``u``.
    """
    # TODO: only the upper surface, need lower surface too.
    u_sub_a = u_sub.vector().get_local()
    u_a     = u.vector().get_local()
    dofmap  = self.submesh_map_dict['Q']
    n       = len(u.function_space().split())

    if n == 0:
      u_a[dofmap] = u_sub_a
    else:
      for i in range(n):
        u_a[i::3][dofmap] = u_sub_a[i::3]
    
    self.assign_variable(u, u_a)
    self.assign_variable(u, self.vert_extrude(u, d='down'))

  def assign_to_submesh_variable(self, u, u_sub):
    r"""
    Assign the values from the variable ``u`` defined on a 3D mesh used
    with a :class:`~model.D3Model` to the submesh variable ``u_sub``.
    """
    u_sub_a = u_sub.vector().get_local()
    u_a     = u.vector().get_local()
    dofmap  = self.submesh_map_dict['Q']
    n       = len(u.function_space().split())

    if n == 0:
      u_sub_a = u_a[dofmap]
    else:
      for i in range(n):
        u_sub_a[i::3] = u_a[i::3][dofmap]

    self.assign_variable(u_sub, u_sub_a)


  def calculate_boundaries(self,
                           mask        = None,
                           adot        = None,
                           U_mask      = None,
                           mark_divide = False,
                           contour     = None):
    """
    Determines the boundaries of the current model mesh
    """
    s = "::: calculating boundaries :::"
    print_text(s, cls=self)

    if    (contour is     None and     mark_divide) \
       or (contour is not None and not mark_divide):
      s = ">>> IF PARAMETER <mark_divide> OF calculate_boundaries() IS " + \
          "TRUE, PARAMETER <contour> MUST BE A NUMPY ARRAY OF COORDINATES " + \
          "OF THE ICE-SHEET EXTERIOR BOUNDARY <<<"
      print_text(s, 'red', 1)
      sys.exit(1)

    elif contour is not None and mark_divide:
      s = "    - marking the interior facets for incomplete meshes -"
      print_text(s, cls=self)
      tree = cKDTree(contour)
      self.contour_tree = tree # save this for ``self.form_dvd_mesh()``
     
    # this function contains markers which may be applied to facets of the mesh
    self.ff      = MeshFunction('size_t', self.mesh, 2, 0)
    self.ff_acc  = MeshFunction('size_t', self.mesh, 2, 0)
    self.cf      = MeshFunction('size_t', self.mesh, 3, 0)
    dofmap       = self.Q.dofmap()
    
    # default to all grounded ice :
    if mask == None:
      mask = Expression('1.0', element=self.Q.ufl_element())
    
    # default to zero accumulation :
    if adot == None:
      adot = Expression('0.0', element=self.Q.ufl_element())
   
    # convert constants to expressions that can be evaluated at (x,y,z) :
    elif type(adot) == Constant or type(adot) == float or type(adot) == int:
      adot = Expression('adot', adot=adot, degree=0)
    
    # default to U observations everywhere :
    if U_mask == None:
      U_mask = Expression('1.0', element=self.Q.ufl_element())

    self.init_adot(adot)
    self.init_mask(mask)
    self.init_U_mask(U_mask)
    
    tol = 1e-6
    
    # iterate through the facets and mark each if on a boundary :
    #
    #   2 = high slope, upward facing ................ grounded surface
    #   3 = grounded high slope, downward facing ..... grounded base
    #   4 = low slope, upward or downward facing ..... sides
    #   5 = floating ................................. floating base
    #   6 = floating ................................. floating surface
    #   7 = floating sides
    #
    # facet for accumulation :
    #
    #   1 = high slope, upward facing ................ positive adot
    s = "    - iterating through %i facets - " % self.num_facets
    print_text(s, cls=self)
    for f in facets(self.mesh):
      n        = f.normal()
      x_m      = f.midpoint().x()
      y_m      = f.midpoint().y()
      z_m      = f.midpoint().z()
      mask_xy  = mask(x_m, y_m, z_m)
      
      if   n.z() >=  tol and f.exterior():
        adot_xy   = adot(x_m, y_m, z_m)
        U_mask_xy = U_mask(x_m, y_m, z_m)
        if adot_xy > 0:
          self.ff_acc[f] = self.GAMMA_ACC
        if mask_xy > 1:
          if U_mask_xy > 0:
            self.ff[f] = self.GAMMA_U_FLT
          else:
            self.ff[f] = self.GAMMA_S_FLT
        else:
          if U_mask_xy > 0:
            self.ff[f] = self.GAMMA_U_GND
          else:
            self.ff[f] = self.GAMMA_S_GND
    
      elif n.z() <= -tol and f.exterior():
        if mask_xy > 1:
          self.ff[f] = self.GAMMA_B_FLT
        else:
          self.ff[f] = self.GAMMA_B_GND
      
      elif n.z() >  -tol and n.z() < tol and f.exterior():
        # if we want to use a basin, we need to mark the interior facets :
        if mark_divide:
          if tree.query((x_m, y_m))[0] < 1000:
            if z_m > 0:
              self.ff[f] = self.GAMMA_L_OVR
            else:
              self.ff[f] = self.GAMMA_L_UDR
          else:
            self.ff[f] = self.GAMMA_L_DVD
        # otherwise just mark for over (4) and under (10) water :
        else:
          if z_m > 0:
            self.ff[f] = self.GAMMA_L_OVR
          else:
            self.ff[f] = self.GAMMA_L_UDR
    
    s = "    - done - "
    print_text(s, cls=self)
    
    s = "    - iterating through %i cells - " % self.num_cells
    print_text(s, cls=self)
    for c in cells(self.mesh):
      x_m     = c.midpoint().x()
      y_m     = c.midpoint().y()
      z_m     = c.midpoint().z()
      mask_xy = mask(x_m, y_m, z_m)

      if mask_xy > 1:
        self.cf[c] = self.OMEGA_FLT
      else:
        self.cf[c] = self.OMEGA_GND
    
    s = "    - done - "
    print_text(s, cls=self)
  
    self.set_measures()

  def set_measures(self):
    """
    set the new measure space for facets ``self.ds`` and cells ``self.dx`` for
    the boundaries marked by FacetFunction ``self.ff`` and CellFunction 
    ``self.cf``, respectively.

    Also, the number of facets marked by 
    :func:`calculate_boundaries` :

    * ``self.N_OMEGA_GND``   -- number of cells marked ``self.OMEGA_GND``  
    * ``self.N_OMEGA_FLT``   -- number of cells marked ``self.OMEGA_FLT``  
    * ``self.N_GAMMA_S_GND`` -- number of facets marked ``self.GAMMA_S_GND``
    * ``self.N_GAMMA_B_GND`` -- number of facets marked ``self.GAMMA_B_GND``
    * ``self.N_GAMMA_S_FLT`` -- number of facets marked ``self.GAMMA_S_FLT``
    * ``self.N_GAMMA_B_FLT`` -- number of facets marked ``self.GAMMA_B_FLT``
    * ``self.N_GAMMA_L_DVD`` -- number of facets marked ``self.GAMMA_L_DVD``
    * ``self.N_GAMMA_L_OVR`` -- number of facets marked ``self.GAMMA_L_OVR``
    * ``self.N_GAMMA_L_UDR`` -- number of facets marked ``self.GAMMA_L_UDR``
    * ``self.N_GAMMA_U_GND`` -- number of facets marked ``self.GAMMA_U_GND``
    * ``self.N_GAMMA_U_FLT`` -- number of facets marked ``self.GAMMA_U_FLT``

    The subdomains corresponding to FacetFunction ``self.ff`` are :

    * ``self.dBed_g``  --  grounded bed
    * ``self.dBed_f``  --  floating bed
    * ``self.dBed``    --  bed
    * ``self.dSrf_gu`` --  grounded with U observations
    * ``self.dSrf_fu`` --  floating with U observations
    * ``self.dSrf_u``  --  surface with U observations
    * ``self.dSrf_g``  --  surface of grounded ice
    * ``self.dSrf_f``  --  surface of floating ice
    * ``self.dSrf``    --  surface
    * ``self.dLat_d``  --  lateral divide
    * ``self.dLat_to`` --  lateral terminus overwater
    * ``self.dLat_tu`` --  lateral terminus underwater
    * ``self.dLat_t``  --  lateral terminus
    * ``self.dLat``    --  lateral

    The subdomains corresponding to CellFunction ``self.cf`` are :

    * ``self.dx_g``    --  internal above grounded
    * ``self.dx_f``    --  internal above floating

    This method will create a :py:class:`dict` called ``self.measures``
    containing all of the :class:`ufl.measure.Measure` instances for 
    this :class:`~model.Model`. 
    """
    # calculate the number of cells and facets that are of a certain type
    # for determining Dirichlet boundaries :
    self.N_OMEGA_GND   = sum(self.cf.array()     == self.OMEGA_GND)
    self.N_OMEGA_FLT   = sum(self.cf.array()     == self.OMEGA_FLT)
    self.N_GAMMA_S_GND = sum(self.ff.array()     == self.GAMMA_S_GND)
    self.N_GAMMA_B_GND = sum(self.ff.array()     == self.GAMMA_B_GND)
    self.N_GAMMA_S_FLT = sum(self.ff.array()     == self.GAMMA_S_FLT)
    self.N_GAMMA_B_FLT = sum(self.ff.array()     == self.GAMMA_B_FLT)
    self.N_GAMMA_L_DVD = sum(self.ff.array()     == self.GAMMA_L_DVD)
    self.N_GAMMA_L_OVR = sum(self.ff.array()     == self.GAMMA_L_OVR)
    self.N_GAMMA_L_UDR = sum(self.ff.array()     == self.GAMMA_L_UDR)
    self.N_GAMMA_U_GND = sum(self.ff.array()     == self.GAMMA_U_GND)
    self.N_GAMMA_U_FLT = sum(self.ff.array()     == self.GAMMA_U_FLT)
    self.N_GAMMA_ACC   = sum(self.ff_acc.array() == self.GAMMA_ACC)

    # create new measures of integration :
    self.ds      = Measure('ds', subdomain_data=self.ff)
    self.dx      = Measure('dx', subdomain_data=self.cf)
    
    self.dx_g    = self.dx(0)                # internal above grounded
    self.dx_f    = self.dx(1)                # internal above floating
    self.dBed_g  = self.ds(3)                # grounded bed
    self.dBed_f  = self.ds(5)                # floating bed
    self.dBed    = self.ds(3) + self.ds(5)   # bed
    self.dSrf_gu = self.ds(8)                # grounded with U observations
    self.dSrf_fu = self.ds(9)                # floating with U observations
    self.dSrf_u  = self.ds(8) + self.ds(9)   # surface with U observations
    self.dSrf_g  = self.ds(2) + self.ds(8)   # surface of grounded ice
    self.dSrf_f  = self.ds(6) + self.ds(9)   # surface of floating ice
    self.dSrf    =   self.ds(6) + self.ds(2) \
                   + self.ds(8) + self.ds(9) # surface
    self.dLat_d  = self.ds(7)                # lateral divide
    self.dLat_to = self.ds(4)                # lateral terminus overwater
    self.dLat_tu = self.ds(10)               # lateral terminus underwater
    self.dLat_t  = self.ds(4) + self.ds(10)  # lateral terminus
    self.dLat    =   self.ds(4) + self.ds(7) \
                   + self.ds(10)             # lateral
    
    self.dOmega     = Boundary(self.dx, [0,1],
                      'entire interior')
    self.dOmega_g   = Boundary(self.dx, [0],
                      'interior above grounded ice')
    self.dOmega_w   = Boundary(self.dx, [1],
                      'interior above floating ice')
    self.dGamma     = Boundary(self.ds, [2,3,4,5,6,7,8,9,2,8,9,10],
                      'entire exterior')
    self.dGamma_bg  = Boundary(self.ds, [3],
                      'grounded basal surface')
    self.dGamma_bw  = Boundary(self.ds, [5],
                      'floating basal surface')
    self.dGamma_b   = Boundary(self.ds, [3,5],
                      'entire basal surface')
    self.dGamma_sgu = Boundary(self.ds, [8],
                      'upper surface with U observations above grounded ice')
    self.dGamma_swu = Boundary(self.ds, [9],
                      'upper surface with U observations above floating ice')
    self.dGamma_su  = Boundary(self.ds, [8,9],
                      'entire upper surface with U observations')
    self.dGamma_sg  = Boundary(self.ds, [2,8],
                      'upper surface above grounded ice')
    self.dGamma_sw  = Boundary(self.ds, [6,9],
                      'upper surface above floating ice')
    self.dGamma_s   = Boundary(self.ds, [6,2,8,9],
                      'entire upper surface')
    self.dGamma_ld  = Boundary(self.ds, [7],
                      'lateral interior surface')
    self.dGamma_lto = Boundary(self.ds, [4],
                      'exterior lateral surface above water')
    self.dGamma_ltu = Boundary(self.ds, [10],
                      'exterior lateral surface below= water')
    self.dGamma_lt  = Boundary(self.ds, [4,10],
                      'entire exterior lateral surface')
    self.dGamma_l   = Boundary(self.ds, [4,7,10],
                      'entire exterior and interior lateral surface')
    self.dGamma_w   = Boundary(self.ds, [4,10,5],
                      'exterior surface in contact with water')

    # save a dictionary of boundaries for later access by user :
    measures = [self.dOmega,
                self.dOmega_g,
                self.dOmega_w,
                self.dGamma,
                self.dGamma_bg,
                self.dGamma_bw,
                self.dGamma_b,
                self.dGamma_sgu,
                self.dGamma_swu,
                self.dGamma_su,
                self.dGamma_sg,
                self.dGamma_sw,
                self.dGamma_s,
                self.dGamma_ld,
                self.dGamma_lto,
                self.dGamma_ltu,
                self.dGamma_lt,
                self.dGamma_l]
    self.measures = {}
    for m in measures:
      self.measures[m.description] = m


  def deform_mesh_to_geometry(self, S, B):
    """
    Deforms the 3D mesh to the geometry from FEniCS Expressions for the 
    surface <S> and bed <B>.
    """
    s = "::: deforming mesh to geometry :::"
    print_text(s, cls=self)

    # initialize the topography functions :
    self.init_S(S)
    self.init_B(B)

    # convert constants to expressions that can be evaluated at (x,y,z) :
    if type(S) == Constant or type(S) == float or type(S) == int:
      S = Expression('S', S=S, degree=0)
    if type(B) == Constant or type(B) == float or type(B) == int:
      B = Expression('B', B=B, degree=0)
    
    # transform z :
    # thickness = surface - base, z = thickness + base
    # Get the height of the mesh, assumes that the base is at z=0
    max_height  = self.mesh.coordinates()[:,2].max()
    min_height  = self.mesh.coordinates()[:,2].min()
    mesh_height = max_height - min_height

    # sigma coordinate :
    self.init_sigma( project((self.x[2] - min_height) / mesh_height, self.Q) )
    
    s = "    - iterating through %i vertices - " % self.num_vertices
    print_text(s, cls=self)
    
    for x in self.mesh.coordinates():
      x[2] = (x[2] / mesh_height) * (S(x[0], x[1], x[2]) - B(x[0], x[1], x[2]))
      x[2] = x[2] + B(x[0], x[1], x[2])
    s = "    - done - "
    print_text(s, cls=self)
      
  def calc_thickness(self):
    """
    Calculate the continuous thickness field which increases from 0 at the 
    surface to the actual thickness at the bed.
    """
    s = "::: calculating z-varying thickness :::"
    print_text(s, cls=self)
    #H = project(self.S - self.x[2], self.Q, annotate=False)
    H          = self.vert_integrate(Constant(1.0), d='down')
    Hv         = H.vector()
    Hv[Hv < 0] = 0.0
    print_min_max(H, 'H', cls=self)
    return H
  
  def solve_hydrostatic_pressure(self, annotate=False, cls=None):
    """
    Solve for the hydrostatic pressure 'p'.
    """
    if cls is None:
      cls = self
    # solve for vertical velocity :
    s  = "::: solving hydrostatic pressure :::"
    print_text(s, cls=cls)
    rhoi   = self.rhoi
    g      = self.g
    p      = self.vert_integrate(rhoi*g, d='down', annotate=annotate)
    pv     = p.vector()
    pv[pv < 0] = 0.0
    self.assign_variable(self.p, p, annotate=annotate)
  
  def vert_extrude(self, u, d='up', Q='self', annotate=False):
    r"""
    This extrudes a function *u* vertically in the direction *d* = 'up' or
    'down'.  It does this by solving a variational problem:
  
    .. math::
       
       \frac{\partial v}{\partial z} = 0 \hspace{10mm}
       v|_b = u

    """
    s = "::: extruding function %swards :::" % d
    print_text(s, cls=self)
    if type(Q) != FunctionSpace:
      #Q  = self.Q_non_periodic
      Q = u.function_space()
    ff   = self.ff
    phi  = TestFunction(Q)
    v    = TrialFunction(Q)
    a    = v.dx(2) * phi * dx
    L    = DOLFIN_EPS * phi * dx
    bcs  = []
    # extrude bed (ff = 3,5) 
    if d == 'up':
      if self.N_GAMMA_B_GND != 0:
        bcs.append(DirichletBC(Q, u, ff, self.GAMMA_B_GND))  # grounded
      if self.N_GAMMA_B_FLT != 0:
        bcs.append(DirichletBC(Q, u, ff, self.GAMMA_B_FLT))  # shelves
    # extrude surface (ff = 2,6) 
    elif d == 'down':
      if self.N_GAMMA_S_GND != 0:
        bcs.append(DirichletBC(Q, u, ff, self.GAMMA_S_GND))  # grounded
      if self.N_GAMMA_S_FLT != 0:
        bcs.append(DirichletBC(Q, u, ff, self.GAMMA_S_FLT))  # shelves
      if self.N_GAMMA_U_GND != 0:
        bcs.append(DirichletBC(Q, u, ff, self.GAMMA_U_GND))  # grounded
      if self.N_GAMMA_U_FLT != 0:
        bcs.append(DirichletBC(Q, u, ff, self.GAMMA_U_FLT))  # shelves
    try:
      name = '%s extruded %s' % (u.name(), d)
    except AttributeError:
      name = 'extruded'
    v    = Function(Q, name=name)
    solve(a == L, v, bcs, annotate=annotate,
          solver_parameters=self.linear_solve_params())
    print_min_max(v, 'extruded function')
    return v
  
  def vert_integrate(self, u, d='up', Q='self', annotate=False):
    """
    Integrate <u> from the bed to the surface.
    """
    s = "::: vertically integrating function :::"
    print_text(s, cls=self)

    if type(Q) != FunctionSpace:
      Q  = self.Q_non_periodic
      #Q = u.function_space()
    ff  = self.ff
    phi = TestFunction(Q)
    v   = TrialFunction(Q)
    bcs = []
    # integral is zero on bed (ff = 3,5) 
    if d == 'up':
      if self.N_GAMMA_B_GND != 0:
        bcs.append(DirichletBC(Q, 0.0, ff, self.GAMMA_B_GND))  # grounded
      if self.N_GAMMA_B_FLT != 0:
        bcs.append(DirichletBC(Q, 0.0, ff, self.GAMMA_B_FLT))  # shelves
      a      = v.dx(2) * phi * dx
    # integral is zero on surface (ff = 2,6) 
    elif d == 'down':
      if self.N_GAMMA_S_GND != 0:
        bcs.append(DirichletBC(Q, 0.0, ff, self.GAMMA_S_GND))  # grounded
      if self.N_GAMMA_S_FLT != 0:
        bcs.append(DirichletBC(Q, 0.0, ff, self.GAMMA_S_FLT))  # shelves
      if self.N_GAMMA_U_GND != 0:
        bcs.append(DirichletBC(Q, 0.0, ff, self.GAMMA_U_GND))  # grounded
      if self.N_GAMMA_U_FLT != 0:
        bcs.append(DirichletBC(Q, 0.0, ff, self.GAMMA_U_FLT))  # shelves
      a      = -v.dx(2) * phi * dx
    L      = u * phi * dx
    name   = 'value integrated %s' % d 
    v      = Function(Q, name=name)
    solve(a == L, v, bcs, annotate=annotate,
          solver_parameters=self.linear_solve_params())
    print_min_max(v, 'vertically integrated function')
    return v

  def calc_vert_average(self, u, annotate=False):
    """
    Calculates the vertical average of a given function *u*.  
    
    :param u: Function to avergage vertically
    :rtype:   the vertical average of *u*
    """
    s = "::: calculating vertical average :::"
    print_text(s, cls=self)

    # vertically integrate the function up and then extrude that down :
    ubar = self.vert_integrate(u,  d='up',   annotate=annotate)
    ubar = self.vert_extrude(ubar, d='down', annotate=annotate)
    
    try:
      name = 'vertical average of %s' % u.name()
    except AttributeError:
      name = 'vertical average'
    ubar.rename(name, '')
   
    # divide by the thickness for vertical average : 
    ubar_v = ubar.vector().get_local()
    S_v    = self.S.vector().get_local()
    B_v    = self.B.vector().get_local()
    H_v    = S_v - B_v + DOLFIN_EPS
    self.assign_variable(ubar, ubar_v / H_v)
    return ubar
 
  def save_bed_mesh(self, h5File): 
    """
    save the basal boundary mesh to hdf5 file <h5File>.
    """
    s = "::: writing 'bedmesh' to supplied hdf5 file :::"
    print_text(s, cls=self.this)
    h5File.write(self.bedmesh, 'bedmesh')

  def save_srf_mesh(self, h5File): 
    """
    save the surface boundary mesh to hdf5 file <h5File>.
    """
    s = "::: writing 'srfmesh' to supplied hdf5 file :::"
    print_text(s, cls=self.this)
    h5File.write(self.srfmesh, 'srfmesh')

  def save_lat_mesh(self, h5File): 
    """
    save the lateral boundary mesh to hdf5 file <h5File>.
    """
    s = "::: writing 'latmesh' to supplied hdf5 file :::"
    print_text(s, cls=self.this)
    h5File.write(self.latmesh, 'latmesh')

  def save_dvd_mesh(self, h5File): 
    """
    save the divide boundary mesh to hdf5 file <h5File>.
    """
    s = "::: writing 'dvdmesh' to supplied hdf5 file :::"
    print_text(s, cls=self.this)
    h5File.write(self.dvdmesh, 'dvdmesh')

  def initialize_variables(self):
    """
    Initializes the class's variables to default values that are then set
    by the individually created model.
    """
    super(D3Model, self).initialize_variables()

    s = "::: initializing 3D variables :::"
    print_text(s, cls=self)

    # Depth below sea level :
    class Depth(Expression):
      def eval(self, values, x):
        values[0] = abs(min(0, x[2]))
    self.D = Depth(element=self.Q.ufl_element())
    
    # age  :  
    self.age           = Function(self.Q, name='age')
    self.a0            = Function(self.Q, name='a0')

    # mass :    
    self.mhat          = Function(self.Q, name='mhat')  # mesh velocity

    # specical dof mapping for periodic spaces :
    if self.use_periodic:
      self.mhat_non = Function(self.Q_non_periodic)
      self.assmhat  = FunctionAssigner(mhat.function_space(),
                                       self.Q_non_periodic)

    # surface climate :
    # TODO: re-implent this (it was taken out somewhere)
    self.precip        = Function(self.Q, name='precip')

  def thermo_solve(self, momentum, energy, wop_kwargs,
                   callback           = None,
                   atol               = 1e2,
                   rtol               = 1e0,
                   max_iter           = 50,
                   iter_save_vars     = None,
                   post_tmc_save_vars = None,
                   starting_i         = 1):
    r""" 
    Perform thermo-mechanical coupling between momentum and energy.

    :param momentum:       momentum instance to couple with ``energy``.
    :param energy:         energy instance to couple with ``momentum``.
                           Currently, the only 3D energy implementation is 
                           :class:`~energy.Enthalpy`.
    :param wop_kwargs:     a :py:class:`~dict` of arguments for
                           water-optimization method 
                           :func:`~energy.Energy.optimize_water_flux`
    :param callback:       a function that is called back at the end of each 
                           iteration
    :param atol:           absolute stopping tolerance 
                           :math:`a_{tol} \leq r = \Vert \theta_n - \theta_{n-1} \Vert`
    :param rtol:           relative stopping tolerance
                           :math:`r_{tol} \leq \Vert r_n - r_{n-1} \Vert`
    :param max_iter:       maximum number of iterations to perform
    :param iter_save_vars: python :py:class:`~list` containing functions to 
                           save each iteration
    :param starting_i:     if you are restarting this process, you may start 
                           it at a later iteration. 
    
    :type momentum:        :class:`~momentum.Momentum`
    :type energy:          :class:`~energy.Energy`
    """
    s    = '::: performing thermo-mechanical coupling with atol = %.2e, ' + \
           'rtol = %.2e, and max_iter = %i :::'
    print_text(s % (atol, rtol, max_iter), cls=self.this)
    
    from cslvr import Momentum
    from cslvr import Energy

    # TODO: also make sure these are D3Model momentum and energy classes. 
    if not isinstance(momentum, Momentum):
      s = ">>> thermo_solve REQUIRES A 'Momentum' INSTANCE, NOT %s <<<"
      print_text(s % type(momentum) , 'red', 1)
      sys.exit(1)
    
    if not isinstance(energy, Energy):
      s = ">>> thermo_solve REQUIRES AN 'Energy' INSTANCE, NOT %s <<<"
      print_text(s % type(energy) , 'red', 1)
      sys.exit(1)

    # mark starting time :
    t0   = time()

    # ensure that we have a steady-state form :
    if energy.transient:
      energy.make_steady_state()

    # retain base install directory :
    out_dir_i = self.out_dir

    # directory for saving convergence history :
    d_hist   = self.out_dir + 'tmc/convergence_history/'
    if not os.path.exists(d_hist) and self.MPI_rank == 0:
      os.makedirs(d_hist)

    # number of digits for saving variables :
    n_i  = len(str(max_iter))
    
    # get the bounds of Fb, the max will be updated based on temperate zones :
    if energy.energy_flux_mode == 'Fb':
      bounds = copy(wop_kwargs['bounds'])
      self.init_Fb_min(bounds[0])
      self.init_Fb_max(bounds[1])
      wop_kwargs['bounds']  = (self.Fb_min, self.Fb_max)

    # L_2 erro norm between iterations :
    abs_error = np.inf
    rel_error = np.inf
      
    # number of iterations, from a starting point (useful for restarts) :
    if starting_i <= 1:
      counter = 1
    else:
      counter = starting_i
   
    # previous velocity for norm calculation
    U_prev    = self.theta.copy(True)

    # perform a fixed-point iteration until the L_2 norm of error 
    # is less than tolerance :
    while abs_error > atol and rel_error > rtol and counter <= max_iter:
       
      # set a new unique output directory :
      out_dir_n = 'tmc/%0*d/' % (n_i, counter)
      self.set_out_dir(out_dir_i + out_dir_n)
      
      # solve velocity :
      momentum.solve(annotate=False)

      # update pressure-melting point :
      energy.calc_T_melt(annotate=False)

      # calculate basal friction heat flux :
      momentum.calc_q_fric()
      
      # derive temperature and temperature-melting flux terms :
      energy.calc_basal_temperature_flux()
      energy.calc_basal_temperature_melting_flux()

      # solve energy steady-state equations to derive temperate zone :
      energy.derive_temperate_zone(annotate=False)
      
      # fixed-point interation for thermal parameters and discontinuous 
      # properties :
      energy.update_thermal_parameters(annotate=False)
      
      # calculate the basal-melting rate :
      energy.solve_basal_melt_rate()
      
      # always initialize Fb to the zero-energy-flux bc :  
      Fb_v = self.Mb.vector().get_local() * self.rhoi(0) / self.rhow(0)
      self.init_Fb(Fb_v)
  
      # update bounds based on temperate zone :
      if energy.energy_flux_mode == 'Fb':
        Fb_m_v                 = self.Fb_max.vector().get_local()
        alpha_v                = self.alpha.vector().get_local()
        Fb_m_v[:]              = DOLFIN_EPS
        Fb_m_v[alpha_v == 1.0] = bounds[1]
        self.init_Fb_max(Fb_m_v)
      
      # optimize the flux of water to remove abnormally high water :
      if energy.energy_flux_mode == 'Fb':
        energy.optimize_water_flux(**wop_kwargs)

      # solve the energy-balance and partition T and W from theta :
      energy.solve(annotate=False)
      
      # calculate L_2 norms :
      abs_error_n  = norm(U_prev.vector() - self.theta.vector(), 'l2')
      tht_nrm      = norm(self.theta.vector(), 'l2')

      # save convergence history :
      if counter == 1:
        rel_error  = abs_error_n
        if self.MPI_rank == 0:
          err_a = np.array([abs_error_n])
          nrm_a = np.array([tht_nrm])
          np.savetxt(d_hist + 'abs_err.txt',    err_a)
          np.savetxt(d_hist + 'theta_norm.txt', nrm_a)
      else:
        rel_error = abs(abs_error - abs_error_n)
        if self.MPI_rank == 0:
          err_n = np.loadtxt(d_hist + 'abs_err.txt')
          nrm_n = np.loadtxt(d_hist + 'theta_norm.txt')
          err_a = np.append(err_n, np.array([abs_error_n]))
          nrm_a = np.append(nrm_n, np.array([tht_nrm]))
          np.savetxt(d_hist + 'abs_err.txt',     err_a)
          np.savetxt(d_hist + 'theta_norm.txt',  nrm_a)

      # print info to screen :
      if self.MPI_rank == 0:
        s0    = '>>> '
        s1    = 'TMC fixed-point iteration %i (max %i) done: ' \
                 % (counter, max_iter)
        s2    = 'r (abs) = %.2e ' % abs_error
        s3    = '(tol %.2e), '    % atol
        s4    = 'r (rel) = %.2e ' % rel_error
        s5    = '(tol %.2e)'      % rtol
        s6    = ' <<<'
        text0 = get_text(s0, 'red', 1)
        text1 = get_text(s1, 'red')
        text2 = get_text(s2, 'red', 1)
        text3 = get_text(s3, 'red')
        text4 = get_text(s4, 'red', 1)
        text5 = get_text(s5, 'red')
        text6 = get_text(s6, 'red', 1)
        print text0 + text1 + text2 + text3 + text4 + text5 + text6

      # call callback function if set :
      if callback != None:
        s    = '::: calling thermo-couple-callback function :::'
        print_text(s, cls=self.this)
        callback(counter)
    
      # save state to unique hdf5 file :
      if isinstance(iter_save_vars, list):
        s    = '::: saving variables in list arg iter_save_vars :::'
        print_text(s, cls=self.this)
        out_file = self.out_dir + 'tmc.h5'
        foutput  = HDF5File(mpi_comm_world(), out_file, 'w')
        for var in iter_save_vars:
          self.save_hdf5(var, f=foutput)
        foutput.close()
      
      # update error stuff and increment iteration counter :
      abs_error    = abs_error_n
      U_prev       = self.theta.copy(True)
      counter     += 1
    
    # reset the base directory ! :
    self.set_out_dir(out_dir_i)
    
    # reset the bounds on Fb :
    if energy.energy_flux_mode == 'Fb':  wop_kwargs['bounds'] = bounds
      
    # save state to unique hdf5 file :
    if isinstance(post_tmc_save_vars, list):
      s    = '::: saving variables in list arg post_tmc_save_vars :::'
      print_text(s, cls=self.this)
      out_file = self.out_dir + 'tmc.h5'
      foutput  = HDF5File(mpi_comm_world(), out_file, 'w')
      for var in post_tmc_save_vars:
        self.save_hdf5(var, f=foutput)
      foutput.close()

    # calculate total time to compute
    tf = time()
    s  = tf - t0
    m  = s / 60.0
    h  = m / 60.0
    s  = s % 60
    m  = m % 60
    text = "time to thermo-couple: %02d:%02d:%02d" % (h,m,s)
    print_text(text, 'red', 1)
       
    # plot the convergence history : 
    s    = "::: convergence info saved to \'%s\' :::"
    print_text(s % d_hist, cls=self.this)
    if self.MPI_rank == 0:
      np.savetxt(d_hist + 'time.txt', np.array([tf - t0]))

      err_a = np.loadtxt(d_hist + 'abs_err.txt')
      nrm_a = np.loadtxt(d_hist + 'theta_norm.txt')
     
      # plot iteration error : 
      fig   = plt.figure()
      ax    = fig.add_subplot(111)
      ax.set_ylabel(r'$\Vert \theta_{n-1} - \theta_n \Vert$')
      ax.set_xlabel(r'iteration')
      ax.plot(err_a, 'k-', lw=2.0)
      plt.grid()
      plt.savefig(d_hist + 'abs_err.png', dpi=100)
      plt.close(fig)
      
      # plot theta norm :
      fig = plt.figure()
      ax  = fig.add_subplot(111)
      ax.set_ylabel(r'$\Vert \theta_n \Vert$')
      ax.set_xlabel(r'iteration')
      ax.plot(nrm_a, 'k-', lw=2.0)
      plt.grid()
      plt.savefig(d_hist + 'theta_norm.png', dpi=100)
      plt.close(fig)

  def update_mesh(self):
    """
    This method will update the surface height ``self.S`` and vertices 
    of deformed mesh ``self.mesh``.
    """
    print_text("    - updating mesh -", cls=self)
    
    # update the mesh :
    sigma                        = self.sigma.compute_vertex_values()
    S                            = self.S.compute_vertex_values()
    B                            = self.B.compute_vertex_values()
    self.mesh.coordinates()[:,2] = sigma*(S - B) + B  # only the z coordinate 

  def transient_iteration(self, momentum, mass, time_step, adaptive, annotate):
    r"""
    This function defines one interation of the transient solution, and is 
    called by the function :func:`~model.transient_solve`.

    Currently, the dolfin-adjoint ``annotate`` is not supported.

    """
    dt        = time_step
    mesh      = self.mesh
    dSdt      = self.dSdt

    def f(S):
      mass.model.init_S(S)
      mass.solve_dSdt()
      return mass.model.dSdt.vector().get_local()

    # calculate velocity :
    momentum.solve()

    # update the mass model's velocity field :
    self.assign_to_submesh_variable(u = self.U3,   u_sub = mass.model.U3)

    # save the initial surface :
    S_0     = self.S.vector().get_local()

    # calculate new surface :
    #mass.solve()

    # impose the thickness limit and update the model's surface :
    S_a         = self.RK4(f, mass.model.S.vector().get_local(), dt)
    B_a         = mass.model.B.vector().get_local()
    thin        = (S_a - B_a) < mass.thklim
    S_a[thin]   = B_a[thin] + mass.thklim
    mass.model.init_S(S_a)

    # update the 3D model's surface :
    self.assign_from_submesh_variable(u = self.S,  u_sub = mass.model.S)

    # save the new surface :
    S_1     = self.S.vector().get_local()

    # deform the mesh :
    self.update_mesh()

    # calculate mesh velocity :
    sigma_a   = self.sigma.vector().get_local()
    mhat_a    = (S_1 - S_0) / dt * sigma_a

    # set mesh velocity depending on periodicity due to the fact that 
    # the topography S and B are always not periodic :
    if self.use_periodic:
      self.assign_variable(self.mhat_non, mhat_a)
      self.assmhat.assign(self.mhat, self.mhat_non, annotate=annotate)
    else:
      self.assign_variable(self.mhat, mhat_a)



