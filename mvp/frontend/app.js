const API = "http://127.0.0.1:8000";
const crops = ["Tomato","Potato","Onion","Wheat","Rice","Cauliflower","Cabbage","Brinjal","Chilli","Mango","Banana"];
const locations = ["Kolkata","Howrah","Hooghly","Nadia","Burdwan"];
const cropEmoji = {Tomato:"🍅",Potato:"🥔",Onion:"🧅",Wheat:"🌾",Rice:"🍚",Cauliflower:"🥦",Cabbage:"🥬",Brinjal:"🍆",Chilli:"🌶️",Mango:"🥭",Banana:"🍌"};
// Session: JWT token + user profile only. NEVER store a password in localStorage.
let token = localStorage.getItem("kdToken") || null;
let user = JSON.parse(localStorage.getItem("kdUser") || "null");
let authMode = "login";
function authHeaders(extra){ return Object.assign({"Content-Type":"application/json"}, token ? {"Authorization":"Bearer "+token} : {}, extra||{}); }
function fillSelect(id, values){document.getElementById(id).innerHTML=values.map(v=>`<option>${v}</option>`).join("")}
["priceCrop","demandCrop","sellCrop"].forEach(id=>fillSelect(id,crops));
["priceLocation","demandLocation","sellLocation"].forEach(id=>fillSelect(id,locations));
function showAuth(){document.getElementById("authModal").classList.remove("hidden");setMode("login")}
function hideAuth(){document.getElementById("authModal").classList.add("hidden")}
function setMode(mode){authMode=mode;document.getElementById("loginTab").classList.toggle("active",mode==="login");document.getElementById("registerTab").classList.toggle("active",mode==="register");document.getElementById("nameWrap").style.display=mode==="register"?"block":"none";document.getElementById("roleWrap").style.display=mode==="register"?"block":"none";document.getElementById("authSubmit").textContent=mode==="login"?"Login":"Create account";document.getElementById("authMessage").textContent=""}
function updateAuth(){
  const area=document.getElementById("authArea");
  const dash=document.getElementById("dashLink");
  if(dash) dash.style.display = (user && user.role==="farmer") ? "" : "none";
  area.innerHTML=user?`<span class="message">Hi, ${escapeHtml(user.name)}</span> <button class="btn ghost" onclick="logout()">Logout</button>`:`<button class="btn ghost" onclick="showAuth()">Login / Register</button>`;
  const orders=document.getElementById("ordersSection"); if(orders) orders.style.display = user ? "" : "none";
  if(user) loadOrders();
}
function logout(){user=null;token=null;localStorage.removeItem("kdUser");localStorage.removeItem("kdToken");updateAuth()}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
async function submitAuth(){
 const body={email:document.getElementById("authEmail").value,password:document.getElementById("authPassword").value};
 if(authMode==="register"){body.name=document.getElementById("authName").value;body.role=document.getElementById("authRole").value}
 try{const r=await fetch(API+(authMode==="login"?"/api/login":"/api/register"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.detail||"Request failed");user={id:d.id,name:d.name,email:d.email,role:d.role};token=d.access_token;localStorage.setItem("kdUser",JSON.stringify(user));localStorage.setItem("kdToken",token);updateAuth();hideAuth();loadProducts()}catch(e){document.getElementById("authMessage").textContent=e.message}
}
async function predict(kind){
 const prefix=kind==="price"?"price":"demand", result=document.getElementById(prefix+"Result");
 const body={crop:document.getElementById(prefix+"Crop").value,season:document.getElementById(prefix+"Season").value,location:document.getElementById(prefix+"Location").value,month:Number(document.getElementById(prefix+"Month").value),rainfall_mm:Number(document.getElementById(prefix+"Rain").value),temperature_c:Number(document.getElementById(prefix+"Temp").value)};
 result.textContent="Calculating estimate…";
 try{const r=await fetch(API+"/api/predict/"+kind,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.detail||"Prediction failed");
 result.innerHTML=kind==="price"?`Estimated price: <strong>₹${d.estimated_price_per_kg}/kg</strong><br>Indicative range: ₹${d.indicative_low}–₹${d.indicative_high}/kg<br><small>${escapeHtml(d.note)}</small>`:`Demand level: <strong>${d.label}</strong><br>Demo demand index: ${d.estimated_demand_index}<br><small>${escapeHtml(d.note)}</small>`;
 }catch(e){result.textContent=e.message+". Is the backend running?"}
}
async function loadProducts(){
 const target=document.getElementById("products"), q=(document.getElementById("search").value||"").toLowerCase();
 try{const r=await fetch(API+"/api/products");const items=await r.json();const filtered=items.filter(p=>p.crop.toLowerCase().includes(q)||p.location.toLowerCase().includes(q));
 target.innerHTML=filtered.length?filtered.map(p=>`<article class="product"><div class="emoji">${cropEmoji[p.crop]||"🌿"}</div><h3>${escapeHtml(p.crop)}</h3><p>📍 ${escapeHtml(p.location)} · ${escapeHtml(p.farmer_name)}</p><p>${p.quantity} kg available</p><div class="price">₹${p.price}/kg</div><p>${escapeHtml(p.description||"Fresh farm produce")}</p>${user && user.role==="customer" ? `<button class="btn primary" onclick="buyProduct(${p.id})">Buy</button>` : ""}</article>`).join(""):`<div class="empty">No listings yet. Farmers can add the first product below.</div>`;
 }catch(e){target.innerHTML='<div class="empty">Marketplace unavailable. Start the backend to load listings.</div>'}
}
async function buyProduct(productId){
 if(!user){showAuth();return}
 if(user.role!=="customer"){alert("Only customer accounts can place orders.");return}
 const qty=Number(prompt("Quantity in kg:", "10"));
 if(!qty || qty<=0) return;
 try{const r=await fetch(API+"/api/orders",{method:"POST",headers:authHeaders(),body:JSON.stringify({product_id:productId,quantity:qty})});const d=await r.json();if(!r.ok)throw Error(d.detail||"Order failed");alert("Order placed! Order #"+d.id);loadProducts();loadOrders()}catch(e){alert(e.message)}
}
async function loadOrders(){
 const box=document.getElementById("ordersList"); if(!box||!token) return;
 try{const r=await fetch(API+"/api/orders",{headers:authHeaders()});const items=await r.json();if(!r.ok)throw Error("Could not load orders");
 box.innerHTML=items.length?items.map(o=>`<div class="product"><h3>Order #${o.id} — ${escapeHtml(o.crop)}</h3><p>${o.quantity} kg · ₹${o.price}/kg · ${escapeHtml(o.location)}</p><p>Status: <strong>${escapeHtml(o.status)}</strong></p></div>`).join(""):`<div class="empty">No orders yet.</div>`}catch(e){box.innerHTML='<div class="empty">'+escapeHtml(e.message)+'</div>'}
}
async function addProduct(){
 const msg=document.getElementById("sellMessage");if(!user){msg.textContent="Please log in as a farmer first.";showAuth();return}if(user.role!=="farmer"){msg.textContent="Only farmer accounts can publish listings.";return}
 const body={crop:document.getElementById("sellCrop").value,quantity:Number(document.getElementById("sellQty").value),price:Number(document.getElementById("sellPrice").value),location:document.getElementById("sellLocation").value,description:document.getElementById("sellDesc").value};
 try{const r=await fetch(API+"/api/products",{method:"POST",headers:authHeaders(),body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.detail||"Could not publish");msg.textContent="Listing published successfully!";loadProducts()}catch(e){msg.textContent=e.message}
}
updateAuth();loadProducts();
